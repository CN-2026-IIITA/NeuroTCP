#include "tcp-rl-env.h"
#include "ns3/tcp-header.h"
#include "ns3/object.h"
#include "ns3/core-module.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/tcp-socket-base.h"
#include <vector>
#include <numeric>
#include <cmath>       // std::log1p, std::max, std::min


namespace ns3 {

NS_LOG_COMPONENT_DEFINE ("ns3::TcpGymEnv");
NS_OBJECT_ENSURE_REGISTERED (TcpGymEnv);

TcpGymEnv::TcpGymEnv ()
{
  NS_LOG_FUNCTION (this);
  SetOpenGymInterface(OpenGymInterface::Get());
}

TcpGymEnv::~TcpGymEnv ()
{
  NS_LOG_FUNCTION (this);
}

TypeId
TcpGymEnv::GetTypeId (void)
{
  static TypeId tid = TypeId ("ns3::TcpGymEnv")
    .SetParent<OpenGymEnv> ()
    .SetGroupName ("OpenGym")
  ;
  return tid;
}

void TcpGymEnv::DoDispose () { NS_LOG_FUNCTION (this); }

void TcpGymEnv::SetNodeId(uint32_t id)     { NS_LOG_FUNCTION (this); m_nodeId     = id; }
void TcpGymEnv::SetSocketUuid(uint32_t id) { NS_LOG_FUNCTION (this); m_socketUuid = id; }

std::string
TcpGymEnv::GetTcpCongStateName(const TcpSocketState::TcpCongState_t state)
{
  switch(state) {
    case TcpSocketState::CA_OPEN:       return "CA_OPEN";
    case TcpSocketState::CA_DISORDER:   return "CA_DISORDER";
    case TcpSocketState::CA_CWR:        return "CA_CWR";
    case TcpSocketState::CA_RECOVERY:   return "CA_RECOVERY";
    case TcpSocketState::CA_LOSS:       return "CA_LOSS";
    case TcpSocketState::CA_LAST_STATE: return "CA_LAST_STATE";
    default:                            return "UNKNOWN";
  }
}

std::string
TcpGymEnv::GetTcpCAEventName(const TcpSocketState::TcpCAEvent_t event)
{
  switch(event) {
    case TcpSocketState::CA_EVENT_TX_START:         return "CA_EVENT_TX_START";
    case TcpSocketState::CA_EVENT_CWND_RESTART:     return "CA_EVENT_CWND_RESTART";
    case TcpSocketState::CA_EVENT_COMPLETE_CWR:     return "CA_EVENT_COMPLETE_CWR";
    case TcpSocketState::CA_EVENT_LOSS:             return "CA_EVENT_LOSS";
    case TcpSocketState::CA_EVENT_ECN_NO_CE:        return "CA_EVENT_ECN_NO_CE";
    case TcpSocketState::CA_EVENT_ECN_IS_CE:        return "CA_EVENT_ECN_IS_CE";
    case TcpSocketState::CA_EVENT_DELAYED_ACK:      return "CA_EVENT_DELAYED_ACK";
    case TcpSocketState::CA_EVENT_NON_DELAYED_ACK:  return "CA_EVENT_NON_DELAYED_ACK";
    default:                                        return "UNKNOWN";
  }
}

Ptr<OpenGymSpace>
TcpGymEnv::GetActionSpace()
{
  uint32_t parameterNum = 2;
  float low  = 0.0;
  float high = 65535;
  std::vector<uint32_t> shape = {parameterNum,};
  std::string dtype = TypeNameGet<uint32_t> ();
  Ptr<OpenGymBoxSpace> box = CreateObject<OpenGymBoxSpace> (low, high, shape, dtype);
  NS_LOG_INFO ("MyGetActionSpace: " << box);
  return box;
}

bool
TcpGymEnv::GetGameOver()
{
  m_isGameOver = false;
  NS_LOG_INFO ("MyGetGameOver: " << m_isGameOver);
  return m_isGameOver;
}

float
TcpGymEnv::GetReward()
{
  NS_LOG_INFO("MyGetReward: " << m_envReward);
  return m_envReward;
}

std::string
TcpGymEnv::GetExtraInfo()
{
  NS_LOG_INFO("MyGetExtraInfo: " << m_info);
  return m_info;
}

bool
TcpGymEnv::ExecuteActions(Ptr<OpenGymDataContainer> action)
{
  Ptr<OpenGymBoxContainer<uint32_t> > box =
      DynamicCast<OpenGymBoxContainer<uint32_t> >(action);
  m_new_ssThresh = box->GetValue(0);
  m_new_cWnd     = box->GetValue(1);
  NS_LOG_INFO ("MyExecuteActions: " << action);
  return true;
}

// ─────────────────────────────────────────────────────────────────────────────
//  TcpEventGymEnv
// ─────────────────────────────────────────────────────────────────────────────

NS_OBJECT_ENSURE_REGISTERED (TcpEventGymEnv);

TcpEventGymEnv::TcpEventGymEnv () : TcpGymEnv() { NS_LOG_FUNCTION (this); }
TcpEventGymEnv::~TcpEventGymEnv ()              { NS_LOG_FUNCTION (this); }

TypeId
TcpEventGymEnv::GetTypeId (void)
{
  static TypeId tid = TypeId ("ns3::TcpEventGymEnv")
    .SetParent<TcpGymEnv> ()
    .SetGroupName ("OpenGym")
    .AddConstructor<TcpEventGymEnv> ()
  ;
  return tid;
}

void TcpEventGymEnv::DoDispose ()               { NS_LOG_FUNCTION (this); }
void TcpEventGymEnv::SetReward(float value)     { NS_LOG_FUNCTION (this); m_reward  = value; }
void TcpEventGymEnv::SetPenalty(float value)    { NS_LOG_FUNCTION (this); m_penalty = value; }

Ptr<OpenGymSpace>
TcpEventGymEnv::GetObservationSpace()
{
  uint32_t parameterNum = 10;
  float low = 0.0, high = 1000000000.0;
  std::vector<uint32_t> shape = {parameterNum,};
  std::string dtype = TypeNameGet<uint64_t> ();
  Ptr<OpenGymBoxSpace> box = CreateObject<OpenGymBoxSpace>(low, high, shape, dtype);
  NS_LOG_INFO ("MyGetObservationSpace: " << box);
  return box;
}

Ptr<OpenGymDataContainer>
TcpEventGymEnv::GetObservation()
{
  uint32_t parameterNum = 10;
  std::vector<uint32_t> shape = {parameterNum,};
  Ptr<OpenGymBoxContainer<uint64_t> > box =
      CreateObject<OpenGymBoxContainer<uint64_t> >(shape);

  box->AddValue(m_socketUuid);
  box->AddValue(0);
  box->AddValue(Simulator::Now().GetMicroSeconds());
  box->AddValue(m_nodeId);
  box->AddValue(m_tcb->m_ssThresh);
  box->AddValue(m_tcb->m_cWnd);
  box->AddValue(m_tcb->m_segmentSize);
  box->AddValue(m_segmentsAcked);
  box->AddValue(m_bytesInFlight);
  box->AddValue(m_rtt.GetMicroSeconds());
  NS_LOG_INFO ("MyGetObservation: " << box);
  return box;
}

void TcpEventGymEnv::TxPktTrace(Ptr<const Packet>, const TcpHeader&, Ptr<const TcpSocketBase>) { NS_LOG_FUNCTION (this); }
void TcpEventGymEnv::RxPktTrace(Ptr<const Packet>, const TcpHeader&, Ptr<const TcpSocketBase>) { NS_LOG_FUNCTION (this); }

uint32_t
TcpEventGymEnv::GetSsThresh(Ptr<const TcpSocketState> tcb, uint32_t bytesInFlight)
{
  NS_LOG_FUNCTION (this);
  m_envReward = m_penalty;
  m_calledFunc    = CalledFunc_t::GET_SS_THRESH;
  m_info          = "GetSsThresh";
  m_tcb           = tcb;
  m_bytesInFlight = bytesInFlight;
  Notify();
  return m_new_ssThresh;
}

void
TcpEventGymEnv::IncreaseWindow(Ptr<TcpSocketState> tcb, uint32_t segmentsAcked)
{
  NS_LOG_FUNCTION (this);
  m_envReward     = m_reward;
  m_calledFunc    = CalledFunc_t::INCREASE_WINDOW;
  m_info          = "IncreaseWindow";
  m_tcb           = tcb;
  m_segmentsAcked = segmentsAcked;
  Notify();
  tcb->m_cWnd = m_new_cWnd;
}

void
TcpEventGymEnv::PktsAcked(Ptr<TcpSocketState> tcb, uint32_t segmentsAcked, const Time& rtt)
{
  NS_LOG_FUNCTION (this);
  m_calledFunc    = CalledFunc_t::PKTS_ACKED;
  m_info          = "PktsAcked";
  m_tcb           = tcb;
  m_segmentsAcked = segmentsAcked;
  m_rtt           = rtt;
}

void
TcpEventGymEnv::CongestionStateSet(Ptr<TcpSocketState> tcb,
                                   const TcpSocketState::TcpCongState_t newState)
{
  NS_LOG_FUNCTION (this);
  m_calledFunc = CalledFunc_t::CONGESTION_STATE_SET;
  m_info       = "CongestionStateSet";
  m_tcb        = tcb;
  m_newState   = newState;
}

void
TcpEventGymEnv::CwndEvent(Ptr<TcpSocketState> tcb,
                          const TcpSocketState::TcpCAEvent_t event)
{
  NS_LOG_FUNCTION (this);
  m_calledFunc = CalledFunc_t::CWND_EVENT;
  m_info       = "CwndEvent";
  m_tcb        = tcb;
  m_event      = event;
}

// ─────────────────────────────────────────────────────────────────────────────
//  TcpTimeStepGymEnv  —  TIME-BASED ENV (used by DQN / PPO)
//
//  FIXES vs v4:
//
//  [A] Reward is computed ONCE in GetObservation() and sent as raw_reward.
//      Python shape_reward() now only clips — no extra penalties added.
//      This eliminates the double-counting of RTT and loss penalties.
//
//  [B] Observation field ORDER corrected and locked:
//        obs[4]  → state[0]  ssThresh
//        obs[5]  → state[1]  cWnd
//        obs[6]  → state[2]  segmentSize    ← was swapped with segmentsAcked
//        obs[7]  → state[3]  segmentsAcked  ← was swapped with segmentSize
//        obs[8]  → state[4]  bytesInFlightAvg
//        obs[9]  → state[5]  lastRtt (avgRtt for compat)
//        obs[10] → state[6]  minRtt  (m_tcb->m_minRtt, NS-3 native)
//        obs[11] → state[7]  avgRtt
//        obs[12] → state[8]  rttVariance (0, placeholder)
//        obs[13] → state[9]  packetLostInStep
//        obs[14] → state[10] retransmissions (0, placeholder)
//        obs[15] → state[11] throughput (bytes/s)
//
//  [C] m_pktLostInStep reset happens AFTER it is recorded in GetObservation().
//
//  [D] RTT guard: only apply rtt_penalty if both avgRtt and minRtt > 1000 μs.
//      If either is zero/corrupt the penalty stays 0 to avoid poisoning reward.
//
//  [E] Reward weights adjusted for single-side computation (no Python addition):
//        tp_score    = log1p(tp) / log1p(1.25e6)   weight: 1.0
//        rtt_penalty = -0.3 * max(0, ratio - 1)    weight: 0.3 (was 0.2; Python added 0.1)
//        loss_penalty= -min(5, 0.8 * pkt_lost)     weight: 0.8 (was 0.5; Python added 0.3)
//      Clipped to [-5, +5] — Python just re-clips to same range.
// ─────────────────────────────────────────────────────────────────────────────

NS_OBJECT_ENSURE_REGISTERED (TcpTimeStepGymEnv);

TcpTimeStepGymEnv::TcpTimeStepGymEnv () : TcpGymEnv()
{
  NS_LOG_FUNCTION (this);
  m_pktLostInStep     = 0;
  m_pktLostTotal      = 0;
  m_prevSsThreshCalls = 0;
}

void
TcpTimeStepGymEnv::ScheduleNextStateRead()
{
  NS_LOG_FUNCTION (this);
  Simulator::Schedule(m_timeStep, &TcpTimeStepGymEnv::ScheduleNextStateRead, this);
  Notify();
}

TcpTimeStepGymEnv::~TcpTimeStepGymEnv () { NS_LOG_FUNCTION (this); }

TypeId
TcpTimeStepGymEnv::GetTypeId (void)
{
  static TypeId tid = TypeId ("ns3::TcpTimeStepGymEnv")
    .SetParent<TcpGymEnv> ()
    .SetGroupName ("OpenGym")
    .AddConstructor<TcpTimeStepGymEnv> ()
  ;
  return tid;
}

void TcpTimeStepGymEnv::DoDispose ()            { NS_LOG_FUNCTION (this); }
void TcpTimeStepGymEnv::SetDuration(Time value) { NS_LOG_FUNCTION (this); m_duration = value; }
void TcpTimeStepGymEnv::SetTimeStep(Time value) { NS_LOG_FUNCTION (this); m_timeStep = value; }
void TcpTimeStepGymEnv::SetReward(float value)  { NS_LOG_FUNCTION (this); m_reward   = value; }
void TcpTimeStepGymEnv::SetPenalty(float value) { NS_LOG_FUNCTION (this); m_penalty  = value; }

Ptr<OpenGymSpace>
TcpTimeStepGymEnv::GetObservationSpace()
{
  // 16 values total; Python strips obs[0:4] (header) leaving STATE_SIZE=12
  uint32_t parameterNum = 16;
  float low = 0.0, high = 1000000000.0;
  std::vector<uint32_t> shape = {parameterNum,};
  std::string dtype = TypeNameGet<uint64_t> ();
  Ptr<OpenGymBoxSpace> box = CreateObject<OpenGymBoxSpace>(low, high, shape, dtype);
  NS_LOG_INFO ("MyGetObservationSpace: " << box);
  return box;
}

Ptr<OpenGymDataContainer>
TcpTimeStepGymEnv::GetObservation()
{
  uint32_t parameterNum = 16;
  std::vector<uint32_t> shape = {parameterNum,};
  Ptr<OpenGymBoxContainer<uint64_t> > box =
      CreateObject<OpenGymBoxContainer<uint64_t> >(shape);

  // ── Header [0–3] — stripped by Python (obs[4:]) ──────────────────────────
  box->AddValue(m_socketUuid);                         // [0]
  box->AddValue(1);                                    // [1] envType
  box->AddValue(Simulator::Now().GetMicroSeconds());   // [2] simTime
  box->AddValue(m_nodeId);                             // [3]

  // ── obs[4:] → Python state indices [0–11] ────────────────────────────────
  // FIX [B]: field order locked and documented — must match Python STATE_SCALE

  // [4]  → state[0]  ssThresh
  box->AddValue(m_tcb->m_ssThresh);

  // [5]  → state[1]  cWnd
  box->AddValue(m_tcb->m_cWnd);

  // [6]  → state[2]  segmentSize  ← FIX [B]: was after segmentsAcked (swapped)
  box->AddValue(m_tcb->m_segmentSize);

  // [7]  → state[3]  segmentsAckedSum  ← FIX [B]: was before segmentSize (swapped)
  uint64_t segAckedSum = std::accumulate(
      m_segmentsAcked.begin(), m_segmentsAcked.end(), 0ULL);
  box->AddValue(segAckedSum);

  // [8]  → state[4]  bytesInFlightAvg
  uint64_t bifSum = std::accumulate(
      m_bytesInFlight.begin(), m_bytesInFlight.end(), 0ULL);
  uint64_t bifAvg = m_bytesInFlight.size()
                    ? bifSum / m_bytesInFlight.size() : 0ULL;
  box->AddValue(bifAvg);

  // Compute avgRtt for this step
  Time avgRtt = Seconds(0.0);
  if (m_rttSampleNum > 0) {
    avgRtt = m_rttSum / m_rttSampleNum;
  }

  // [9]  → state[5]  lastRtt (avgRtt used here for compatibility)
  box->AddValue(avgRtt.GetMicroSeconds());

  // [10] → state[6]  minRtt — NS-3 native tracker (m_tcb->m_minRtt)
  //        Python reads this as next_raw[6] for reward diagnostics.
  box->AddValue(m_tcb->m_minRtt.GetMicroSeconds());

  // [11] → state[7]  avgRtt
  box->AddValue(avgRtt.GetMicroSeconds());

  // [12] → state[8]  rttVariance (placeholder — 0)
  box->AddValue(0ULL);

  // [13] → state[9]  packetLostInStep
  //        FIX [C]: read BEFORE reset below
  box->AddValue((uint64_t)m_pktLostInStep);

  // [14] → state[10] retransmissions (placeholder — 0)
  box->AddValue(0ULL);

  // [15] → state[11] throughput (bytes/s)
  float throughput = 0.0f;
  if (m_timeStep.GetSeconds() > 0) {
    throughput = (float)(segAckedSum * m_tcb->m_segmentSize)
                 / (float)m_timeStep.GetSeconds();
  }
  box->AddValue((uint64_t)throughput);

  // ── Reward computation — single source of truth ───────────────────────────
  //
  // FIX [A]: Python shape_reward() now only clips — it does NOT add its own
  // RTT or loss penalties.  All reward signal is computed here, once.
  //
  // FIX [E]: Weights raised to absorb the Python-side penalties that were
  // removed:
  //   rtt_penalty  weight: 0.3  (was 0.2 here + 0.1 Python = 0.3 total)
  //   loss_penalty weight: 0.8  (was 0.5 here + 0.3 Python = 0.8 total)
  //
  // FIX [D]: RTT guard — only apply rtt_penalty if both avgRtt and minRtt
  //   are > 1000 μs (1 ms).  Zero/corrupt values produce no penalty,
  //   preventing reward poisoning at the start of each episode.

  float tp_score    = std::log1p(throughput) / std::log1p(1.25e6f);
  float rtt_penalty = 0.0f;

  uint64_t minRttUs = m_tcb->m_minRtt.GetMicroSeconds();
  uint64_t avgRttUs = avgRtt.GetMicroSeconds();

  if (avgRttUs > 1000 && minRttUs > 1000) {
    // FIX [E]: weight raised from 0.2 → 0.3 (absorbs removed Python 0.1)
    float rtt_ratio = (float)avgRttUs / (float)minRttUs;
    rtt_penalty     = -0.3f * std::max(0.0f, rtt_ratio - 1.0f);
  }
  // If avgRtt or minRtt is zero/corrupt → rtt_penalty stays 0.0

  float loss_penalty = 0.0f;
  if (m_pktLostInStep > 0) {
    // FIX [E]: weight raised from 0.5 → 0.8 (absorbs removed Python 0.3)
    loss_penalty = -std::min(5.0f, 0.8f * (float)m_pktLostInStep);
  }

  // Final reward = tp_score + rtt_penalty + loss_penalty, clipped to [-5, +5]
  // Python receives this as raw_reward and only re-clips to the same range.
  float reward = tp_score + rtt_penalty + loss_penalty;
  m_envReward  = std::max(-5.0f, std::min(5.0f, reward));

  NS_LOG_INFO("GetObservation reward=" << m_envReward
    << " tp="         << tp_score
    << " rtt_pen="    << rtt_penalty
    << " loss_pen="   << loss_penalty
    << " pkt_lost="   << m_pktLostInStep
    << " avgRtt_us="  << avgRttUs
    << " minRtt_us="  << minRttUs
    << " throughput=" << throughput);

  // ── Update accumulators ───────────────────────────────────────────────────
  m_totalAvgRttSum += avgRtt;
  m_totalAvgRttNum++;
  m_old_cWnd = m_new_cWnd;

  // Reset per-step buffers
  m_bytesInFlight.clear();
  m_segmentsAcked.clear();
  m_rttSampleNum     = 0;
  m_rttSum           = MicroSeconds(0.0);
  m_interTxTimeNum   = 0;
  m_interTxTimeSum   = MicroSeconds(0.0);
  m_interRxTimeNum   = 0;
  m_interRxTimeSum   = MicroSeconds(0.0);

  // FIX [C]: reset per-step loss counter AFTER it has been recorded above
  m_pktLostInStep = 0;

  NS_LOG_INFO ("MyGetObservation: " << box);
  return box;
}

void
TcpTimeStepGymEnv::TxPktTrace(Ptr<const Packet>, const TcpHeader&,
                               Ptr<const TcpSocketBase>)
{
  NS_LOG_FUNCTION (this);
  if (m_lastPktTxTime > MicroSeconds(0.0)) {
    Time interTxTime  = Simulator::Now() - m_lastPktTxTime;
    m_interTxTimeSum += interTxTime;
    m_interTxTimeNum++;
  }
  m_lastPktTxTime = Simulator::Now();
}

void
TcpTimeStepGymEnv::RxPktTrace(Ptr<const Packet>, const TcpHeader&,
                               Ptr<const TcpSocketBase>)
{
  NS_LOG_FUNCTION (this);
  if (m_lastPktRxTime > MicroSeconds(0.0)) {
    Time interRxTime  = Simulator::Now() - m_lastPktRxTime;
    m_interRxTimeSum += interRxTime;
    m_interRxTimeNum++;
  }
  m_lastPktRxTime = Simulator::Now();
}

uint32_t
TcpTimeStepGymEnv::GetSsThresh(Ptr<const TcpSocketState> tcb,
                                uint32_t bytesInFlight)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId
    << " GetSsThresh (LOSS EVENT), BytesInFlight: " << bytesInFlight);

  m_tcb = tcb;
  m_bytesInFlight.push_back(bytesInFlight);

  // FIX [C]: increment per-step loss counter on every loss event
  m_pktLostInStep++;
  m_pktLostTotal++;

  if (!m_started) {
    m_started = true;
    Notify();
    ScheduleNextStateRead();
  }

  return m_new_ssThresh;
}

void
TcpTimeStepGymEnv::IncreaseWindow(Ptr<TcpSocketState> tcb,
                                  uint32_t segmentsAcked)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId
    << " IncreaseWindow, SegmentsAcked: " << segmentsAcked);

  m_tcb = tcb;
  m_segmentsAcked.push_back(segmentsAcked);
  m_bytesInFlight.push_back(tcb->m_bytesInFlight);

  if (!m_started) {
    m_started = true;
    Notify();
    ScheduleNextStateRead();
  }

  tcb->m_cWnd = m_new_cWnd;
}

void
TcpTimeStepGymEnv::PktsAcked(Ptr<TcpSocketState> tcb,
                              uint32_t segmentsAcked, const Time& rtt)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId
    << " PktsAcked, SegmentsAcked: " << segmentsAcked << " Rtt: " << rtt);
  m_tcb = tcb;
  m_rttSum += rtt;
  m_rttSampleNum++;
}

void
TcpTimeStepGymEnv::CongestionStateSet(Ptr<TcpSocketState> tcb,
                                      const TcpSocketState::TcpCongState_t newState)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId
    << " CongestionStateSet: " << GetTcpCongStateName(newState));
  m_tcb = tcb;
}

void
TcpTimeStepGymEnv::CwndEvent(Ptr<TcpSocketState> tcb,
                             const TcpSocketState::TcpCAEvent_t event)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId
    << " CwndEvent: " << GetTcpCAEventName(event));
}

} // namespace ns3