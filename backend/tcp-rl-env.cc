/**
 * @file tcp-rl-env.cc
 * @brief Implementation of the TcpGymEnv base class.
 *
 * Provides the core OpenGym environment logic shared by all TCP RL
 * environment variants. This includes action space definition (2-param
 * box for ssThresh and cWnd), game-over checking, reward retrieval,
 * action execution, and utility methods for converting NS-3 TCP
 * congestion state/event enums to human-readable strings.
 */

#include "tcp-rl-env.h"
#include "ns3/tcp-header.h"
#include "ns3/object.h"
#include "ns3/core-module.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/tcp-socket-base.h"
#include <vector>
#include <numeric>


namespace ns3 {

NS_LOG_COMPONENT_DEFINE ("ns3::TcpGymEnv");
NS_OBJECT_ENSURE_REGISTERED (TcpGymEnv);

/*
 * 
 *  TcpGymEnv — Constructor / Destructor / TypeId
 * 
 */

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

void
TcpGymEnv::DoDispose ()
{
  NS_LOG_FUNCTION (this);
}

/*
 * 
 *  Node / Socket Identification
 * 
 */

void
TcpGymEnv::SetNodeId(uint32_t id)
{
  NS_LOG_FUNCTION (this);
  m_nodeId = id;
}

void
TcpGymEnv::SetSocketUuid(uint32_t id)
{
  NS_LOG_FUNCTION (this);
  m_socketUuid = id;
}

/*
 * 
 *  Helper: Convert TCP congestion state enum to readable string
 * 
 */

std::string
TcpGymEnv::GetTcpCongStateName(const TcpSocketState::TcpCongState_t state)
{
  std::string stateName = "UNKNOWN";
  switch(state) {
    case TcpSocketState::CA_OPEN:
      stateName = "CA_OPEN";
      break;
    case TcpSocketState::CA_DISORDER:
      stateName = "CA_DISORDER";
      break;
    case TcpSocketState::CA_CWR:
      stateName = "CA_CWR";
      break;
    case TcpSocketState::CA_RECOVERY:
      stateName = "CA_RECOVERY";
      break;
    case TcpSocketState::CA_LOSS:
      stateName = "CA_LOSS";
      break;
    case TcpSocketState::CA_LAST_STATE:
      stateName = "CA_LAST_STATE";
      break;
    default:
       stateName = "UNKNOWN";
       break;
  }
  return stateName;
}

/*
 * 
 *  Helper: Convert TCP CA event enum to readable string
 * 
 */

std::string
TcpGymEnv::GetTcpCAEventName(const TcpSocketState::TcpCAEvent_t event)
{
  std::string eventName = "UNKNOWN";
  switch(event) {
    case TcpSocketState::CA_EVENT_TX_START:
      eventName = "CA_EVENT_TX_START";
      break;
    case TcpSocketState::CA_EVENT_CWND_RESTART:
      eventName = "CA_EVENT_CWND_RESTART";
      break;
    case TcpSocketState::CA_EVENT_COMPLETE_CWR:
      eventName = "CA_EVENT_COMPLETE_CWR";
      break;
    case TcpSocketState::CA_EVENT_LOSS:
      eventName = "CA_EVENT_LOSS";
      break;
    case TcpSocketState::CA_EVENT_ECN_NO_CE:
      eventName = "CA_EVENT_ECN_NO_CE";
      break;
    case TcpSocketState::CA_EVENT_ECN_IS_CE:
      eventName = "CA_EVENT_ECN_IS_CE";
      break;
    case TcpSocketState::CA_EVENT_DELAYED_ACK:
      eventName = "CA_EVENT_DELAYED_ACK";
      break;
    case TcpSocketState::CA_EVENT_NON_DELAYED_ACK:
      eventName = "CA_EVENT_NON_DELAYED_ACK";
      break;
    default:
       eventName = "UNKNOWN";
       break;
  }
  return eventName;
}

/*
 * 
 *  OpenGym Interface: Action Space
 *
 *  The action space is a Box with 2 uint32 parameters:
 *    [0] = new ssThresh value
 *    [1] = new cWnd value
 *  Range: [0, 65535]
 * 
 */

Ptr<OpenGymSpace>
TcpGymEnv::GetActionSpace()
{
  uint32_t parameterNum = 2;
  float low = 0.0;
  float high = 65535;
  std::vector<uint32_t> shape = {parameterNum,};
  std::string dtype = TypeNameGet<uint32_t> ();

  Ptr<OpenGymBoxSpace> box = CreateObject<OpenGymBoxSpace> (low, high, shape, dtype);
  NS_LOG_INFO ("MyGetActionSpace: " << box);
  return box;
}

/*
 * 
 *  OpenGym Interface: Game Over
 *
 *  Returns false under normal operation. Contains a debug
 *  counter that can be toggled for testing (terminates after
 *  10 steps if the test flag is enabled).
 * 
 */

bool
TcpGymEnv::GetGameOver()
{
  m_isGameOver = false;
  bool test = false;
  static float stepCounter = 0.0;
  stepCounter += 1;
  if (stepCounter == 10 && test) {
      m_isGameOver = true;
  }
  NS_LOG_INFO ("MyGetGameOver: " << m_isGameOver);
  return m_isGameOver;
}

/*
 * 
 *  OpenGym Interface: Reward
 *
 *  Returns the reward value computed by the active subclass.
 *  The subclass sets m_envReward based on its own reward logic
 *  (e.g., positive for ACK, negative for loss).
 * 
 */

float
TcpGymEnv::GetReward()
{
  NS_LOG_INFO("MyGetReward: " << m_envReward);
  return m_envReward;
}

/*
 * 
 *  OpenGym Interface: Extra Info
 *
 *  Returns a descriptive string about the most recent callback
 *  (e.g., "GetSsThresh", "IncreaseWindow"). Useful for the
 *  Python agent to know which TCP event triggered this step.
 * 
 */

std::string
TcpGymEnv::GetExtraInfo()
{
  NS_LOG_INFO("MyGetExtraInfo: " << m_info);
  return m_info;
}

/*
 * 
 *  OpenGym Interface: Execute Actions
 *
 *  Reads the 2-parameter action from the agent:
 *    action[0] → new slow start threshold (ssThresh)
 *    action[1] → new congestion window size (cWnd)
 *  These values are stored and applied in the subclass's
 *  GetSsThresh / IncreaseWindow callbacks.
 * 
 */

bool
TcpGymEnv::ExecuteActions(Ptr<OpenGymDataContainer> action)
{
  Ptr<OpenGymBoxContainer<uint32_t> > box = DynamicCast<OpenGymBoxContainer<uint32_t> >(action);
  m_new_ssThresh = box->GetValue(0);
  m_new_cWnd = box->GetValue(1);

  NS_LOG_INFO ("MyExecuteActions: " << action);
  return true;
}

/*
 * 
 *  TcpEventGymEnv — Event-Driven RL Environment
 *
 *  Notifies the Python agent on every TCP congestion event.
 *  Each notification carries a 10-parameter observation of the
 *  instantaneous TCP state at the moment of the event.
 * 
 */

NS_OBJECT_ENSURE_REGISTERED (TcpEventGymEnv);

TcpEventGymEnv::TcpEventGymEnv () : TcpGymEnv()
{
  NS_LOG_FUNCTION (this);
}

TcpEventGymEnv::~TcpEventGymEnv ()
{
  NS_LOG_FUNCTION (this);
}

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

void
TcpEventGymEnv::DoDispose ()
{
  NS_LOG_FUNCTION (this);
}

void
TcpEventGymEnv::SetReward(float value)
{
  NS_LOG_FUNCTION (this);
  m_reward = value;
}

void
TcpEventGymEnv::SetPenalty(float value)
{
  NS_LOG_FUNCTION (this);
  m_penalty = value;
}

/*
 * Observation space: 10-parameter box of uint64 values.
 * Parameters: socketUuid, envType, simTime, nodeId, ssThresh,
 *             cWnd, segmentSize, segmentsAcked, bytesInFlight, rtt
 */
Ptr<OpenGymSpace>
TcpEventGymEnv::GetObservationSpace()
{
  uint32_t parameterNum = 10;
  float low = 0.0;
  float high = 1000000000.0;
  std::vector<uint32_t> shape = {parameterNum,};
  std::string dtype = TypeNameGet<uint64_t> ();

  Ptr<OpenGymBoxSpace> box = CreateObject<OpenGymBoxSpace> (low, high, shape, dtype);
  NS_LOG_INFO ("MyGetObservationSpace: " << box);
  return box;
}

/*
 * Collect the current TCP state snapshot as a 10-element observation.
 * Values are packed as uint64 for compatibility with the Gym interface.
 */
Ptr<OpenGymDataContainer>
TcpEventGymEnv::GetObservation()
{
  uint32_t parameterNum = 10;
  std::vector<uint32_t> shape = {parameterNum,};

  Ptr<OpenGymBoxContainer<uint64_t> > box = CreateObject<OpenGymBoxContainer<uint64_t> >(shape);

  box->AddValue(m_socketUuid);
  box->AddValue(0);                                     // envType = 0 (event-based)
  box->AddValue(Simulator::Now().GetMicroSeconds ());    // current simulation time
  box->AddValue(m_nodeId);
  box->AddValue(m_tcb->m_ssThresh);
  box->AddValue(m_tcb->m_cWnd);
  box->AddValue(m_tcb->m_segmentSize);
  box->AddValue(m_segmentsAcked);
  box->AddValue(m_bytesInFlight);
  box->AddValue(m_rtt.GetMicroSeconds ());
  NS_LOG_INFO ("MyGetObservation: " << box);
  return box;
}

/*
 * Packet trace callbacks — no-op for the event-based variant since
 * observations are triggered by congestion events, not individual packets.
 */
void
TcpEventGymEnv::TxPktTrace(Ptr<const Packet>, const TcpHeader&, Ptr<const TcpSocketBase>)
{
  NS_LOG_FUNCTION (this);
}

void
TcpEventGymEnv::RxPktTrace(Ptr<const Packet>, const TcpHeader&, Ptr<const TcpSocketBase>)
{
  NS_LOG_FUNCTION (this);
}

/*
 * GetSsThresh — called when packet loss is detected.
 * Assigns the penalty reward and notifies the agent immediately.
 * Returns the agent's chosen ssThresh value.
 */
uint32_t
TcpEventGymEnv::GetSsThresh (Ptr<const TcpSocketState> tcb, uint32_t bytesInFlight)
{
  NS_LOG_FUNCTION (this);
  // Loss detected — assign penalty reward
  m_envReward = m_penalty;

  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " GetSsThresh, BytesInFlight: " << bytesInFlight);
  m_calledFunc = CalledFunc_t::GET_SS_THRESH;
  m_info = "GetSsThresh";
  m_tcb = tcb;
  m_bytesInFlight = bytesInFlight;
  Notify();
  return m_new_ssThresh;
}

/*
 * IncreaseWindow — called when an ACK is received successfully.
 * Assigns the positive reward, notifies the agent, and applies the
 * agent's chosen cWnd value to the TCP socket.
 */
void
TcpEventGymEnv::IncreaseWindow (Ptr<TcpSocketState> tcb, uint32_t segmentsAcked)
{
  NS_LOG_FUNCTION (this);
  // ACK received — assign positive reward
  m_envReward = m_reward;

  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " IncreaseWindow, SegmentsAcked: " << segmentsAcked);
  m_calledFunc = CalledFunc_t::INCREASE_WINDOW;
  m_info = "IncreaseWindow";
  m_tcb = tcb;
  m_segmentsAcked = segmentsAcked;
  Notify();
  tcb->m_cWnd = m_new_cWnd;
}

/*
 * PktsAcked — record RTT sample from acknowledged packets.
 * Does not trigger a Notify; state is stored for the next observation.
 */
void
TcpEventGymEnv::PktsAcked (Ptr<TcpSocketState> tcb, uint32_t segmentsAcked, const Time& rtt)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " PktsAcked, SegmentsAcked: " << segmentsAcked << " Rtt: " << rtt);
  m_calledFunc = CalledFunc_t::PKTS_ACKED;
  m_info = "PktsAcked";
  m_tcb = tcb;
  m_segmentsAcked = segmentsAcked;
  m_rtt = rtt;
}

/*
 * CongestionStateSet — log the new congestion state.
 * Does not trigger a Notify; used for observation context.
 */
void
TcpEventGymEnv::CongestionStateSet (Ptr<TcpSocketState> tcb, const TcpSocketState::TcpCongState_t newState)
{
  NS_LOG_FUNCTION (this);
  std::string stateName = GetTcpCongStateName(newState);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " CongestionStateSet: " << newState << " " << stateName);

  m_calledFunc = CalledFunc_t::CONGESTION_STATE_SET;
  m_info = "CongestionStateSet";
  m_tcb = tcb;
  m_newState = newState;
}

/*
 * CwndEvent — log the congestion window event.
 * Does not trigger a Notify; used for observation context.
 */
void
TcpEventGymEnv::CwndEvent (Ptr<TcpSocketState> tcb, const TcpSocketState::TcpCAEvent_t event)
{
  NS_LOG_FUNCTION (this);
  std::string eventName = GetTcpCAEventName(event);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " CwndEvent: " << event << " " << eventName);

  m_calledFunc = CalledFunc_t::CWND_EVENT;
  m_info = "CwndEvent";
  m_tcb = tcb;
  m_event = event;
}


/*
 * 
 *  TcpTimeStepGymEnv — Timestep-Based RL Environment
 *
 *  Collects TCP statistics over fixed time windows and sends
 *  aggregated observations to the agent periodically. This
 *  provides smoother, less noisy observations compared to the
 *  event-driven variant.
 * 
 */

NS_OBJECT_ENSURE_REGISTERED (TcpTimeStepGymEnv);

TcpTimeStepGymEnv::TcpTimeStepGymEnv () : TcpGymEnv()
{
  NS_LOG_FUNCTION (this);
}

/*
 * Schedule the next periodic observation read.
 * Called after ScheduleNextStateRead re-schedules itself at each
 * m_timeStep interval, forming a continuous observation loop.
 */
void
TcpTimeStepGymEnv::ScheduleNextStateRead ()
{
  NS_LOG_FUNCTION (this);
  Simulator::Schedule (m_timeStep, &TcpTimeStepGymEnv::ScheduleNextStateRead, this);
  Notify();
}

TcpTimeStepGymEnv::~TcpTimeStepGymEnv ()
{
  NS_LOG_FUNCTION (this);
}

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

void
TcpTimeStepGymEnv::DoDispose ()
{
  NS_LOG_FUNCTION (this);
}

void
TcpTimeStepGymEnv::SetDuration(Time value)
{
  NS_LOG_FUNCTION (this);
  m_duration = value;
}

void
TcpTimeStepGymEnv::SetTimeStep(Time value)
{
  NS_LOG_FUNCTION (this);
  m_timeStep = value;
}

void
TcpTimeStepGymEnv::SetReward(float value)
{
  NS_LOG_FUNCTION (this);
  m_reward = value;
}

void
TcpTimeStepGymEnv::SetPenalty(float value)
{
  NS_LOG_FUNCTION (this);
  m_penalty = value;
}

/*
 * Observation space: 16-parameter box of uint64 values.
 * Parameters:
 *   [0]  socketUuid          [1]  envType (1 = timestep)
 *   [2]  simTime             [3]  nodeId
 *   [4]  ssThresh            [5]  cWnd
 *   [6]  segmentSize         [7]  bytesInFlightSum
 *   [8]  bytesInFlightAvg    [9]  segmentsAckedSum
 *   [10] segmentsAckedAvg    [11] avgRtt
 *   [12] minRtt              [13] avgInterTxTime
 *   [14] avgInterRxTime      [15] throughput (bytes/s)
 */
Ptr<OpenGymSpace>
TcpTimeStepGymEnv::GetObservationSpace()
{
  uint32_t parameterNum = 16;
  float low = 0.0;
  float high = 1000000000.0;
  std::vector<uint32_t> shape = {parameterNum,};
  std::string dtype = TypeNameGet<uint64_t> ();

  Ptr<OpenGymBoxSpace> box = CreateObject<OpenGymBoxSpace> (low, high, shape, dtype);
  NS_LOG_INFO ("MyGetObservationSpace: " << box);
  return box;
}

/*
 * Collect aggregated TCP statistics over the current time step
 * and pack them into a 16-element observation vector.
 */
Ptr<OpenGymDataContainer>
TcpTimeStepGymEnv::GetObservation()
{
  uint32_t parameterNum = 16;
  std::vector<uint32_t> shape = {parameterNum,};

  Ptr<OpenGymBoxContainer<uint64_t> > box = CreateObject<OpenGymBoxContainer<uint64_t> >(shape);

  box->AddValue(m_socketUuid);
  box->AddValue(1);                                     // envType = 1 (timestep-based)
  box->AddValue(Simulator::Now().GetMicroSeconds ());    // current simulation time
  box->AddValue(m_nodeId);
  box->AddValue(m_tcb->m_ssThresh);
  box->AddValue(m_tcb->m_cWnd);
  box->AddValue(m_tcb->m_segmentSize);

  // Aggregated bytesInFlight: sum and average
  uint64_t bytesInFlightSum = std::accumulate(m_bytesInFlight.begin(), m_bytesInFlight.end(), 0);
  box->AddValue(bytesInFlightSum);

  uint64_t bytesInFlightAvg = 0;
  if (m_bytesInFlight.size()) {
    bytesInFlightAvg = bytesInFlightSum / m_bytesInFlight.size();
  }
  box->AddValue(bytesInFlightAvg);

  // Aggregated segmentsAcked: sum and average
  uint64_t segmentsAckedSum = std::accumulate(m_segmentsAcked.begin(), m_segmentsAcked.end(), 0);
  box->AddValue(segmentsAckedSum);

  uint64_t segmentsAckedAvg = 0;
  if (m_segmentsAcked.size()) {
    segmentsAckedAvg = segmentsAckedSum / m_segmentsAcked.size();
  }
  box->AddValue(segmentsAckedAvg);

  // Average RTT over the time step
  Time avgRtt = Seconds(0.0);
  if(m_rttSampleNum) {
    avgRtt = m_rttSum / m_rttSampleNum;
  }
  box->AddValue(avgRtt.GetMicroSeconds ());

  // Minimum RTT observed by the socket
  box->AddValue(m_tcb->m_minRtt.GetMicroSeconds ());

  // Average inter-packet transmission time
  Time avgInterTx = Seconds(0.0);
  if (m_interTxTimeNum) {
    avgInterTx = m_interTxTimeSum / m_interTxTimeNum;
  }
  box->AddValue(avgInterTx.GetMicroSeconds ());

  // Average inter-packet reception time
  Time avgInterRx = Seconds(0.0);
  if (m_interRxTimeNum) {
    avgInterRx = m_interRxTimeSum / m_interRxTimeNum;
  }
  box->AddValue(avgInterRx.GetMicroSeconds ());

  // Throughput in bytes/s over this time step
  float throughput = (segmentsAckedSum * m_tcb->m_segmentSize) / m_timeStep.GetSeconds();
  box->AddValue(throughput);


  /*
   * Reward Logic:
   *   - If the agent increased cWnd AND the running average RTT
   *     is >= current avgRtt (i.e., RTT dropped) → positive reward
   *   - If the agent increased cWnd but RTT got worse → penalty
   *   - If cWnd was unchanged → zero reward (neutral)
   */
  if (m_new_cWnd > m_old_cWnd && m_totalAvgRttSum.GetSeconds() > 0 && avgRtt.GetSeconds() > 0)  {
    // Agent chose to increase the congestion window
    if ((m_totalAvgRttSum / m_totalAvgRttNum) >= avgRtt)  {
      // Average RTT decreased — good decision, reward the agent
      m_envReward = m_reward;
    } else {
      // Average RTT increased — penalize the agent
      m_envReward = m_penalty;
    }
  } else  {
    // cWnd was not increased — no reward or penalty
    m_envReward = 0;
  }

  // Update running average RTT for comparison in future steps
  m_totalAvgRttSum += avgRtt;
  m_totalAvgRttNum++;

  // Track the previous cWnd to detect changes next step
  m_old_cWnd = m_new_cWnd;


  NS_LOG_INFO ("MyGetObservation: " << box);

  // Clear accumulators for the next time step
  m_bytesInFlight.clear();
  m_segmentsAcked.clear();

  m_rttSampleNum = 0;
  m_rttSum = MicroSeconds (0.0);

  m_interTxTimeNum = 0;
  m_interTxTimeSum = MicroSeconds (0.0);

  m_interRxTimeNum = 0;
  m_interRxTimeSum = MicroSeconds (0.0);
  
  return box;
}

/*
 * TxPktTrace — track inter-packet transmission timing.
 * Computes the time difference between consecutive transmitted packets
 * and accumulates the sum and count for averaging.
 */
void
TcpTimeStepGymEnv::TxPktTrace(Ptr<const Packet>, const TcpHeader&, Ptr<const TcpSocketBase>)
{
  NS_LOG_FUNCTION (this);
  if ( m_lastPktTxTime > MicroSeconds(0.0) ) {
    Time interTxTime = Simulator::Now() - m_lastPktTxTime;
    m_interTxTimeSum += interTxTime;
    m_interTxTimeNum++;
  }

  m_lastPktTxTime = Simulator::Now();
}

/*
 * RxPktTrace — track inter-packet reception timing.
 * Computes the time difference between consecutive received packets
 * and accumulates the sum and count for averaging.
 */
void
TcpTimeStepGymEnv::RxPktTrace(Ptr<const Packet>, const TcpHeader&, Ptr<const TcpSocketBase>)
{
  NS_LOG_FUNCTION (this);
  if ( m_lastPktRxTime > MicroSeconds(0.0) ) {
    Time interRxTime = Simulator::Now() - m_lastPktRxTime;
    m_interRxTimeSum +=  interRxTime;
    m_interRxTimeNum++;
  }

  m_lastPktRxTime = Simulator::Now();
}

/*
 * GetSsThresh — called on packet loss detection.
 * Stores the TCP control block and bytesInFlight, then triggers
 * the first Notify + ScheduleNextStateRead on the initial call.
 * Returns the agent's chosen ssThresh value.
 */
uint32_t
TcpTimeStepGymEnv::GetSsThresh (Ptr<const TcpSocketState> tcb, uint32_t bytesInFlight)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " GetSsThresh, BytesInFlight: " << bytesInFlight);
  m_tcb = tcb;
  m_bytesInFlight.push_back(bytesInFlight);

  if (!m_started) {
    m_started = true;
    Notify();
    ScheduleNextStateRead();
  }

  // action
  return m_new_ssThresh;
}

/*
 * IncreaseWindow — called on ACK receipt.
 * Stores the TCP control block and accumulated stats, then triggers
 * the first Notify + ScheduleNextStateRead on the initial call.
 * Applies the agent's chosen cWnd value to the socket.
 */
void
TcpTimeStepGymEnv::IncreaseWindow (Ptr<TcpSocketState> tcb, uint32_t segmentsAcked)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " IncreaseWindow, SegmentsAcked: " << segmentsAcked);
  m_tcb = tcb;
  m_segmentsAcked.push_back(segmentsAcked);
  m_bytesInFlight.push_back(tcb->m_bytesInFlight);

  if (!m_started) {
    m_started = true;
    Notify();
    ScheduleNextStateRead();
  }
  // action
  tcb->m_cWnd = m_new_cWnd;
}

/*
 * PktsAcked — accumulate RTT samples from acknowledged packets.
 * These samples are averaged in GetObservation() at each time step.
 */
void
TcpTimeStepGymEnv::PktsAcked (Ptr<TcpSocketState> tcb, uint32_t segmentsAcked, const Time& rtt)
{
  NS_LOG_FUNCTION (this);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " PktsAcked, SegmentsAcked: " << segmentsAcked << " Rtt: " << rtt);
  m_tcb = tcb;
  m_rttSum += rtt;
  m_rttSampleNum++;
}

/*
 * CongestionStateSet — log the TCP congestion state transition.
 * Stores the TCB reference for observation but does not trigger Notify.
 */
void
TcpTimeStepGymEnv::CongestionStateSet (Ptr<TcpSocketState> tcb, const TcpSocketState::TcpCongState_t newState)
{
  NS_LOG_FUNCTION (this);
  std::string stateName = GetTcpCongStateName(newState);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " CongestionStateSet: " << newState << " " << stateName);
  m_tcb = tcb;
}

/*
 * CwndEvent — log the congestion window event.
 * Does not trigger Notify; used only for diagnostic logging.
 */
void
TcpTimeStepGymEnv::CwndEvent (Ptr<TcpSocketState> tcb, const TcpSocketState::TcpCAEvent_t event)
{
  NS_LOG_FUNCTION (this);
  std::string eventName = GetTcpCAEventName(event);
  NS_LOG_INFO(Simulator::Now() << " Node: " << m_nodeId << " CwndEvent: " << event << " " << eventName);
}

} // namespace ns3
