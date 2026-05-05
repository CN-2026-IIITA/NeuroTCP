#include <iostream>
#include <fstream>
#include <string>
#include <algorithm> // Required for std::min
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/point-to-point-layout-module.h"
#include "ns3/applications-module.h"
#include "ns3/error-model.h"
#include "ns3/tcp-header.h"
#include "ns3/enum.h"
#include "ns3/event-id.h"
#include "ns3/flow-monitor-helper.h"
#include "ns3/ipv4-global-routing-helper.h"
#include "ns3/traffic-control-module.h"
#include "ns3/tcp-cubic.h"
  
#include "ns3/opengym-module.h"
#include "tcp-rl.h"
#include "tcp-rl-env.h"

using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("TcpVariantsComparison");

static std::vector<uint32_t> rxPkts;

// static void
// CountRxPkts(uint32_t sinkId, Ptr<const Packet> packet, const Address & srcAddr)
// {
//   rxPkts[sinkId]++;
// }

static void
PrintRxCount()
{
  uint32_t size = rxPkts.size();
  NS_LOG_UNCOND("RxPkts:");
  for (uint32_t i=0; i<size; i++){
    NS_LOG_UNCOND("---SinkId: "<< i << " RxPkts: " << rxPkts.at(i));
  }
}
struct PerformanceMetrics {
  double time;
  double throughput;
  double avgRtt;
  uint32_t packetLoss;
  double NEP;
  double WBI;
};

// This map will store the stats from the previous interval.
static std::map<FlowId, FlowMonitor::FlowStats> g_lastStats;

void CollectMetrics(Ptr<FlowMonitor> monitor, double interval, std::vector<PerformanceMetrics>* metrics, double duration) {
    double currentTime = Simulator::Now().GetSeconds();
    monitor->CheckForLostPackets(); // Update lost packet counts
    auto currentStats = monitor->GetFlowStats();

    uint64_t intervalTxBytes = 0;
    uint64_t intervalRxBytes = 0;
    Time intervalDelaySum = Seconds(0);
    uint32_t intervalRxPackets = 0;
    uint32_t intervalLostPackets = 0;

    // Aggregate stats across all flows for this interval
    for (auto const& kv : currentStats) {
        FlowId flowId = kv.first;
        const auto& s = kv.second;

        // Find the stats from the last interval for this flow
        auto it = g_lastStats.find(flowId);
        if (it != g_lastStats.end()) {
            // This flow existed in the last interval, so calculate the delta
            const auto& last_s = it->second;
            intervalTxBytes += (s.txBytes >= last_s.txBytes) ? (s.txBytes - last_s.txBytes) : s.txBytes;
            intervalRxBytes += (s.rxBytes >= last_s.rxBytes) ? (s.rxBytes - last_s.rxBytes) : s.rxBytes;
            intervalDelaySum += (s.delaySum >= last_s.delaySum) ? (s.delaySum - last_s.delaySum) : s.delaySum;
            intervalRxPackets += (s.rxPackets >= last_s.rxPackets) ? (s.rxPackets - last_s.rxPackets) : s.rxPackets;
            intervalLostPackets += (s.lostPackets >= last_s.lostPackets) ? (s.lostPackets - last_s.lostPackets) : s.lostPackets;
        } else {
            // This is a new flow, delta is the current value
            intervalTxBytes += s.txBytes;
            intervalRxBytes += s.rxBytes;
            intervalDelaySum += s.delaySum;
            intervalRxPackets += s.rxPackets;
            intervalLostPackets += s.lostPackets;
        }
    }

    // Update the global last stats map for the next interval call
    g_lastStats = currentStats;

    // Calculate and store the metrics for this interval
    if (interval > 0) {
        double throughput_bps = (intervalRxBytes * 8.0) / interval;
        double avgRtt_s = (intervalRxPackets > 0) ? (intervalDelaySum.GetSeconds() / intervalRxPackets) : 0.0;

        // NEP and WBI are typically calculated over the total simulation run,
        // as interval-based values can be noisy. We will use the cumulative values for these.
        uint64_t totalTxBytes = 0;
        uint64_t totalRxBytes = 0;
        for (auto const& kv : currentStats) {
            totalTxBytes += kv.second.txBytes;
            totalRxBytes += kv.second.rxBytes;
        }
        double nep = (totalRxBytes > 0) ? (static_cast<double>(totalTxBytes) / totalRxBytes) : 0.0;
        double wbi = (totalTxBytes > 0) ? (static_cast<double>(totalTxBytes - totalRxBytes) / totalTxBytes) : 0.0;

        PerformanceMetrics pm = {
            currentTime,
            throughput_bps,
            avgRtt_s,
            intervalLostPackets, // Packet loss in this interval
            nep,
            wbi
        };
        metrics->push_back(pm);
    }

    // Schedule the next collection if the simulation is not over
    if (Simulator::Now() + Seconds(interval) < Seconds(duration)) {
        Simulator::Schedule(Seconds(interval), &CollectMetrics, monitor, interval, metrics, duration);
    }
}


void SaveMetricsToFiles(const std::vector<PerformanceMetrics>& metrics) {
    // Time, Throughput, RTT, Packet Loss dosyası
    std::ofstream mainFile("result.txt");
    mainFile << "Time (s), Throughput (bps), Average RTT (s), Packet Loss (packets)\n";
    for (const auto& m : metrics) {
        mainFile << m.time << ", "
                 << m.throughput << ", "
                 << m.avgRtt << ", "
                 << m.packetLoss << "\n";
    }
    mainFile.close();

    // NEP ve WBI dosyası
    std::ofstream nepWbiFile("nep_wbi_metrics.txt");
    nepWbiFile << "Time (s), NEP, WBI\n";
    for (const auto& m : metrics) {
        nepWbiFile << m.time << ", "
                   << m.NEP << ", "
                   << m.WBI << "\n";
    }
    nepWbiFile.close();
}


int main (int argc, char *argv[]) 
{
  uint32_t openGymPort = 5555;
  double tcpEnvTimeStep = 0.1;

  uint32_t nLeaf = 1;
  std::string transport_prot = "TcpRl";

  double error_p = 0.0;
  std::string bottleneck_bandwidth = "2Mbps";
  std::string bottleneck_delay = "10ms";
  std::string access_bandwidth = "10Mbps";
  std::string access_delay = "20ms";
  double duration = 10.0;
  
  std::string prefix_file_name = "TcpVariantsComparison";
  uint64_t data_mbytes = 0;
  uint32_t mtu_bytes = 1500;
  uint32_t run = 0;
  // bool flow_monitor = true;
  bool sack = true;
  std::string queue_disc_type = "ns3::PfifoFastQueueDisc";
  std::string recovery = "ns3::TcpClassicRecovery";

  double rew = 1.0;
  double pen = -0.5;

  CommandLine cmd;


  cmd.AddValue ("transport_prot", "Transport protocol to use: TcpNewReno, TcpRlTimeBased", transport_prot);
  cmd.AddValue ("duration", "Simulation duration in seconds", duration);
  cmd.AddValue ("openGymPort", "Port for OpenGym communication", openGymPort);
  cmd.AddValue ("bottleneck_bandwidth", "Bottleneck link bandwidth", bottleneck_bandwidth);
  cmd.AddValue ("bottleneck_delay", "Bottleneck link delay", bottleneck_delay);
  cmd.AddValue ("access_bandwidth", "Access link bandwidth", access_bandwidth);
  cmd.AddValue ("access_delay", "Access link delay", access_delay);
  cmd.AddValue ("error_p", "Packet error rate", error_p);

  cmd.Parse (argc, argv);

  transport_prot = std::string ("ns3::") + transport_prot;

  SeedManager::SetSeed (1);
  SeedManager::SetRun (run);

// TCP olarak hangi algoritma kullanılacağını seçiyor
  NS_LOG_UNCOND("Ns3Env parameters:");
  if (transport_prot.compare ("ns3::TcpRlTimeBased") == 0)
  {
    NS_LOG_UNCOND("--openGymPort: " << openGymPort);
  } else {
    NS_LOG_UNCOND("--openGymPort: No OpenGym");
  }

  NS_LOG_UNCOND("--seed: " << run);
  NS_LOG_UNCOND("--Tcp version: " << transport_prot);



  // OpenGym Env ns3-gym için gerekli ortam 
  Ptr<OpenGymInterface> openGymInterface;
  if (transport_prot.compare ("ns3::TcpRlTimeBased") == 0)
  {
    openGymInterface = OpenGymInterface::Get(openGymPort);
    Config::SetDefault ("ns3::TcpRlTimeBased::StepTime", TimeValue (Seconds(tcpEnvTimeStep))); // adım değeri
    Config::SetDefault ("ns3::TcpRlTimeBased::Duration", TimeValue (Seconds(duration))); // zaman değeri
    Config::SetDefault ("ns3::TcpRlTimeBased::Reward", DoubleValue (rew)); // ödül
    Config::SetDefault ("ns3::TcpRlTimeBased::Penalty", DoubleValue (pen)); // ceza
  }

  // Calculate the ADU size
  Header* temp_header = new Ipv4Header ();
  uint32_t ip_header = temp_header->GetSerializedSize ();
  NS_LOG_LOGIC ("IP Header size is: " << ip_header);
  delete temp_header;
  temp_header = new TcpHeader ();
  uint32_t tcp_header = temp_header->GetSerializedSize ();
  NS_LOG_LOGIC ("TCP Header size is: " << tcp_header);
  delete temp_header;
  uint32_t tcp_adu_size = mtu_bytes - 20 - (ip_header + tcp_header);
  NS_LOG_LOGIC ("TCP ADU size is: " << tcp_adu_size);

  
  double start_time = 0.1; 
  double stop_time = start_time + duration;

  // 4 MB  TCP buffer
  Config::SetDefault ("ns3::TcpSocket::RcvBufSize", UintegerValue (1 << 21));
  Config::SetDefault ("ns3::TcpSocket::SndBufSize", UintegerValue (1 << 21));
  Config::SetDefault ("ns3::TcpSocketBase::Sack", BooleanValue (sack));
  
  Config::SetDefault ("ns3::TcpSocket::DelAckCount", UintegerValue (2));


  Config::SetDefault ("ns3::TcpL4Protocol::RecoveryType",
                      TypeIdValue (TypeId::LookupByName (recovery)));
  

if (transport_prot.compare("ns3::TcpNewReno") == 0) {
    Config::SetDefault ("ns3::TcpL4Protocol::SocketType", TypeIdValue (TcpNewReno::GetTypeId ()));
}
else if (transport_prot.compare("ns3::TcpCubic") == 0) {
    Config::SetDefault ("ns3::TcpL4Protocol::SocketType", TypeIdValue (TcpCubic::GetTypeId ()));
}
else {
    TypeId tcpTid;
    NS_ABORT_MSG_UNLESS (TypeId::LookupByNameFailSafe (transport_prot, &tcpTid), "TypeId " << transport_prot << " not found");
    Config::SetDefault ("ns3::TcpL4Protocol::SocketType", TypeIdValue (TypeId::LookupByName (transport_prot)));
}



  // error modeli kurulumu
  Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable> ();
  uv->SetStream (50);
  RateErrorModel error_model;
  error_model.SetRandomVariable (uv);
  error_model.SetUnit (RateErrorModel::ERROR_UNIT_PACKET);
  error_model.SetRate (error_p);

  //  point-to-point bağlantılarını kur
  PointToPointHelper bottleNeckLink;
  bottleNeckLink.SetDeviceAttribute  ("DataRate", StringValue (bottleneck_bandwidth));
  bottleNeckLink.SetChannelAttribute ("Delay", StringValue (bottleneck_delay));

  PointToPointHelper pointToPointLeaf;
  pointToPointLeaf.SetDeviceAttribute  ("DataRate", StringValue (access_bandwidth));
  pointToPointLeaf.SetChannelAttribute ("Delay", StringValue (access_delay));

  PointToPointDumbbellHelper d (nLeaf, pointToPointLeaf,
                                nLeaf, pointToPointLeaf,
                                bottleNeckLink);

  // Ip stacklerini yükle 
  InternetStackHelper stack;
  stack.InstallAll ();


  TrafficControlHelper tchPfifo;
  tchPfifo.SetRootQueueDisc ("ns3::PfifoFastQueueDisc");



  DataRate access_b (access_bandwidth);
  DataRate bottle_b (bottleneck_bandwidth);
  Time access_d (access_delay);
  Time bottle_d (bottleneck_delay);

  uint32_t size = static_cast<uint32_t>((std::min (access_b, bottle_b).GetBitRate () / 8) *
    ((access_d + bottle_d + access_d) * 2).GetSeconds ());

  Config::SetDefault ("ns3::PfifoFastQueueDisc::MaxSize",
                      QueueSizeValue (QueueSize (QueueSizeUnit::PACKETS, size / mtu_bytes)));

    tchPfifo.Install (d.GetLeft()->GetDevice(1));
    tchPfifo.Install (d.GetRight()->GetDevice(1));
  

  // Ip adresi atamaları
  d.AssignIpv4Addresses (Ipv4AddressHelper ("10.1.1.0", "255.255.255.0"),
                         Ipv4AddressHelper ("10.2.1.0", "255.255.255.0"),
                         Ipv4AddressHelper ("10.3.1.0", "255.255.255.0"));


  NS_LOG_INFO ("Initialize Global Routing.");
  Ipv4GlobalRoutingHelper::PopulateRoutingTables ();

  // sağ ve sol node'lara veri atamaları  
  uint16_t port = 50000;
  Address sinkLocalAddress (InetSocketAddress (Ipv4Address::GetAny (), port));
  PacketSinkHelper sinkHelper ("ns3::TcpSocketFactory", sinkLocalAddress);
  ApplicationContainer sinkApps;
  for (uint32_t i = 0; i < d.RightCount (); ++i)
  {
    sinkHelper.SetAttribute ("Protocol", TypeIdValue (TcpSocketFactory::GetTypeId ()));
    sinkApps.Add (sinkHelper.Install (d.GetRight (i)));
  }
  sinkApps.Start (Seconds (0.0));
  sinkApps.Stop  (Seconds (stop_time));

  for (uint32_t i = 0; i < d.LeftCount (); ++i)
  {
    
    AddressValue remoteAddress (InetSocketAddress (d.GetRightIpv4Address (i), port));
    Config::SetDefault ("ns3::TcpSocket::SegmentSize", UintegerValue (tcp_adu_size));
    BulkSendHelper ftp ("ns3::TcpSocketFactory", Address ());
    ftp.SetAttribute ("Remote", remoteAddress);
    ftp.SetAttribute ("SendSize", UintegerValue (tcp_adu_size));
    ftp.SetAttribute ("MaxBytes", UintegerValue (data_mbytes * 1000000));

    ApplicationContainer clientApp = ftp.Install (d.GetLeft (i));
    clientApp.Start (Seconds (start_time * i)); 
    clientApp.Stop (Seconds (stop_time - 3)); 
  }

    FlowMonitorHelper flowHelper;
    Ptr<FlowMonitor> monitor = flowHelper.InstallAll();
    
    std::vector<PerformanceMetrics> metrics;
    
    
    Simulator::Schedule(Seconds(0.1), &CollectMetrics, monitor, 0.1, &metrics, duration);  
    Simulator::Stop(Seconds(duration));
    Simulator::Run();  
  
    monitor->CheckForLostPackets();

    SaveMetricsToFiles(metrics);


  if ( transport_prot.compare ("ns3::TcpRlTimeBased") == 0)
  {
    openGymInterface->NotifySimulationEnd();
  }

  PrintRxCount();
  Simulator::Destroy ();
  return 0;
}
