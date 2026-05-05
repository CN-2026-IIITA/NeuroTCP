import {
  Activity,
  BarChart3,
  BrainCircuit,
  Cpu,
  Database,
  GitBranch,
  Layers3,
  LineChart,
  Network,
  RadioTower,
  Server,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

type ArchitectureNode = {
  title: string;
  description: string;
  icon: LucideIcon;
  tone: string;
  items: string[];
};

type Contribution = {
  name: string;
  focus: string;
  delivery: string;
};

const metrics = [
  {
    label: "DRL throughput",
    value: "9.498 Mbps",
    detail: "Average from included result set",
  },
  { label: "DRL RTT", value: "14.844 ms", detail: "Lowest measured latency" },
  {
    label: "Packet loss",
    value: "76 packets",
    detail: "Lower than Cubic and NewReno",
  },
  {
    label: "Evaluation set",
    value: "3 variants",
    detail: "DRL-TCP, Cubic, NewReno",
  },
];

const highLevelArchitecture: ArchitectureNode[] = [
  {
    title: "NS-3 simulation",
    description:
      "Builds the network path, runs TCP flows, and records transport behavior under controlled bottleneck conditions.",
    icon: Network,
    tone: "border-blue-500/30 bg-blue-500/10 text-blue-200",
    items: [
      "Dumbbell topology",
      "BulkSend traffic",
      "PacketSink receivers",
      "FlowMonitor metrics",
    ],
  },
  {
    title: "OpenGym bridge",
    description:
      "Converts TCP internals into observations and forwards agent-selected congestion decisions back into NS-3.",
    icon: GitBranch,
    tone: "border-zinc-500/30 bg-zinc-500/10 text-zinc-100",
    items: [
      "TcpRlBase",
      "TcpEventGymEnv",
      "TcpTimeStepGymEnv",
      "Observation and action spaces",
    ],
  },
  {
    title: "DRL control plane",
    description:
      "Trains and evaluates DQN/PPO controllers that adjust cWnd and ssThresh from live TCP state.",
    icon: BrainCircuit,
    tone: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
    items: [
      "DQN agent",
      "PPO agent",
      "Reward feedback",
      "Saved model artifacts",
    ],
  },
];

const sequenceSteps = [
  {
    lane: "Simulation",
    actor: "NS-3 runtime",
    detail:
      "Starts the configured TCP variant, installs applications, advances the simulator clock, and emits TCP callbacks.",
  },
  {
    lane: "TCP socket",
    actor: "TcpRl / TcpRlTimeBased",
    detail:
      "Intercepts ACK, RTT, congestion-state, and loss events through NS-3 congestion-control hooks.",
  },
  {
    lane: "Environment",
    actor: "OpenGym env",
    detail:
      "Builds an event-based or timestep-based observation vector and computes reward or penalty for the latest interval.",
  },
  {
    lane: "Agent",
    actor: "Python DRL policy",
    detail:
      "Chooses a discrete congestion-window action: keep, increase, conservative decrease, or rapid increase.",
  },
  {
    lane: "Metrics",
    actor: "FlowMonitor and parser",
    detail:
      "Writes throughput, RTT, packet loss, NEP, and WBI to result files for analysis and dashboard rendering.",
  },
];

const moduleLayers = [
  {
    title: "Interface and visualization layer",
    icon: LineChart,
    modules: [
      "Next.js app router pages",
      "Recharts comparison views",
      "React Flow DQN view",
      "Framer Motion transitions",
    ],
  },
  {
    title: "API and telemetry layer",
    icon: Server,
    modules: [
      "FastAPI service",
      "Metrics routes",
      "Simulation command route",
      "WebSocket live stream",
      "ZeroMQ subscriber",
    ],
  },
  {
    title: "Simulation and learning layer",
    icon: Cpu,
    modules: [
      "NS-3 C++ simulation",
      "TCP RL congestion ops",
      "OpenGym environments",
      "DQN and PPO Python agents",
    ],
  },
  {
    title: "Artifact and analysis layer",
    icon: Database,
    modules: [
      "Result CSV files",
      "Training history",
      "Keras model files",
      "Matplotlib comparison plots",
    ],
  },
];

const pipelineStages = [
  {
    title: "Configure experiment",
    detail:
      "Choose TCP variant, duration, bottleneck bandwidth, delay, MTU, reward, and penalty values.",
    outputs: ["waf command", "transport protocol", "network parameters"],
  },
  {
    title: "Collect observations",
    detail:
      "Expose socket UUID, cWnd, ssThresh, segment size, ACK samples, bytes in flight, RTT, and throughput.",
    outputs: ["event observations", "timestep observations", "reward signal"],
  },
  {
    title: "Train policy",
    detail:
      "Update the DQN or PPO policy from reward feedback while balancing exploration and exploitation.",
    outputs: ["model files", "training logs", "reward history"],
  },
  {
    title: "Evaluate baselines",
    detail:
      "Run DRL-TCP, Cubic, and NewReno against the same topology and compare throughput, RTT, and packet loss.",
    outputs: ["result files", "statistical comparison", "plots"],
  },
  {
    title: "Present results",
    detail:
      "Serve metrics through the API and visualize system behavior in the dashboard.",
    outputs: ["dashboard charts", "live telemetry", "summary metrics"],
  },
];

const stack = [
  ["Simulation", "NS-3, C++, FlowMonitor, OpenGym/ns3-gym"],
  ["Learning", "Python, TensorFlow/Keras, DQN, PPO, NumPy"],
  ["Analysis", "Pandas, SciPy, Matplotlib, CSV and TSV outputs"],
  ["Backend", "FastAPI, Uvicorn, ZeroMQ, WebSocket APIs"],
  [
    "Frontend",
    "Next.js 14, React, TypeScript, Tailwind CSS, Recharts, React Flow, Framer Motion",
  ],
  ["Deployment", "Docker, Docker Compose"],
];

const contributions: Contribution[] = [
  {
    name: "Shivam Kumar",
    focus: "OpenGym environment bridge",
    delivery:
      "Designed the base TCP Gym environment, event-driven environment, timestep environment, reward logic, and congestion callback integration.",
  },
  {
    name: "Tushar Saharan",
    focus: "NS-3 simulation and metrics",
    delivery:
      "Implemented the simulation skeleton, TCP configuration, dumbbell topology, application setup, FlowMonitor collection, and CSV result output.",
  },
  {
    name: "Varun Pandey",
    focus: "Analysis and telemetry",
    delivery:
      "Built metrics parsing, statistical comparison, graph generation, simulation result datasets, and live dashboard telemetry integration.",
  },
  {
    name: "Kunal Khandelwal",
    focus: "TCP RL algorithm and UI pages",
    delivery:
      "Implemented TCP RL congestion-control variants and contributed comparison, training, and configuration dashboard pages.",
  },
  {
    name: "Aryan Pandey",
    focus: "API and dashboard foundation",
    delivery:
      "Created the FastAPI and frontend scaffold, dashboard experience, animated views, commit tracker, CORS handling, and API port alignment.",
  },
  {
    name: "Chinmay Raheja",
    focus: "Agent results and final evaluation",
    delivery:
      "Implemented DQN and PPO agent work, baseline comparison runs, training artifacts, agent result summaries, and final comparison plots.",
  },
];

const limitations = [
  "The project is a simulation-first research prototype and is not a production TCP stack.",
  "Observed gains depend on topology, bottleneck rate, queue behavior, reward design, and training configuration.",
  "A learned policy may need retraining before it generalizes to unseen RTT, bandwidth, loss, or traffic distributions.",
  "Dashboard telemetry is only as reliable as the active NS-3/OpenGym and API runtime behind it.",
  "The kernel module is experimental and requires separate validation before any real networking use.",
];

function SectionHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="border-b border-zinc-800 pb-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
        {eyebrow}
      </p>
      <h2 className="mt-2 text-2xl font-bold tracking-tight text-white md:text-3xl">
        {title}
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-400">
        {description}
      </p>
    </div>
  );
}

function NodeCard({ node }: { node: ArchitectureNode }) {
  const Icon = node.icon;
  return (
    <div className={`rounded-lg border p-5 ${node.tone}`}>
      <div className="mb-4 flex items-center gap-3">
        <div className="rounded-md border border-white/10 bg-black/30 p-2">
          <Icon className="h-5 w-5" />
        </div>
        <h3 className="text-base font-semibold text-white">{node.title}</h3>
      </div>
      <p className="text-sm leading-6 text-zinc-300">{node.description}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {node.items.map((item) => (
          <Badge
            key={item}
            variant="outline"
            className="border-white/10 bg-black/20 text-[11px] text-zinc-300"
          >
            {item}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export default function DocumentationPage() {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-10 pb-16">
      <section className="relative overflow-hidden rounded-xl border border-zinc-800 bg-black px-6 py-10 md:px-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.08),transparent_34%)]" />
        <div className="relative max-w-4xl">
          <div className="mb-5 flex flex-wrap gap-2">
            <Badge variant="outline" className="border-zinc-700 text-zinc-300">
              Project documentation
            </Badge>
            <Badge variant="outline" className="border-zinc-700 text-zinc-300">
              NS-3 + OpenGym
            </Badge>
            <Badge variant="outline" className="border-zinc-700 text-zinc-300">
              Deep RL TCP
            </Badge>
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-white md:text-6xl">
            NeuroTCP System Documentation
          </h1>
          <p className="mt-5 max-w-3xl text-sm leading-7 text-zinc-400 md:text-base">
            A complete technical reference for the DRL-TCP project:
            architecture, runtime flow, module ownership, experiment pipeline,
            technology stack, results, references, and known limitations. The
            architecture section follows the supplied Eraser workspace structure
            and keeps the documentation aligned with the dashboard theme.
          </p>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {metrics.map((metric) => (
          <Card
            key={metric.label}
            className="rounded-xl border-zinc-800 bg-zinc-950/80 p-5"
          >
            <p className="text-xs uppercase tracking-widest text-zinc-500">
              {metric.label}
            </p>
            <p className="mt-3 text-2xl font-bold text-white">{metric.value}</p>
            <p className="mt-2 text-xs leading-5 text-zinc-500">
              {metric.detail}
            </p>
          </Card>
        ))}
      </section>

      <section className="flex flex-col gap-6">
        <SectionHeader
          eyebrow="Architecture from Eraser"
          title="1. High-Level System Architecture"
          description="This view mirrors the top-level Eraser architecture: the simulator, OpenGym bridge, and DRL control plane form a closed congestion-control loop."
        />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {highLevelArchitecture.map((node) => (
            <NodeCard key={node.title} node={node} />
          ))}
        </div>
        <Card className="rounded-xl border-zinc-800 bg-black p-5">
          <div className="grid grid-cols-1 gap-3 text-sm text-zinc-300 md:grid-cols-5">
            {[
              "TCP state",
              "OpenGym observation",
              "Agent action",
              "cWnd update",
              "FlowMonitor metrics",
            ].map((step, index) => (
              <div
                key={step}
                className="rounded-lg border border-zinc-800 bg-zinc-950 p-4"
              >
                <span className="text-xs text-zinc-500">Step {index + 1}</span>
                <p className="mt-2 font-medium text-white">{step}</p>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section className="flex flex-col gap-6">
        <SectionHeader
          eyebrow="Architecture from Eraser"
          title="2. Control-Loop Sequence Architecture"
          description="This sequence view documents how simulator events move through TCP hooks, environment logic, agent inference, and result collection."
        />
        <Card className="rounded-xl border-zinc-800 bg-black p-5">
          <div className="space-y-3">
            {sequenceSteps.map((step, index) => (
              <div
                key={step.lane}
                className="grid grid-cols-1 gap-3 rounded-lg border border-zinc-800 bg-zinc-950 p-4 md:grid-cols-[160px_220px_1fr]"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-700 bg-black text-xs font-bold text-zinc-300">
                    {index + 1}
                  </div>
                  <span className="text-xs uppercase tracking-widest text-zinc-500">
                    {step.lane}
                  </span>
                </div>
                <p className="font-semibold text-white">{step.actor}</p>
                <p className="text-sm leading-6 text-zinc-400">{step.detail}</p>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section className="flex flex-col gap-6">
        <SectionHeader
          eyebrow="Architecture from Eraser"
          title="3. Module and Deployment Architecture"
          description="This layered architecture maps the repository into interface, API, simulation, learning, and artifact responsibilities."
        />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {moduleLayers.map((layer) => {
            const Icon = layer.icon;
            return (
              <Card
                key={layer.title}
                className="rounded-xl border-zinc-800 bg-black p-5"
              >
                <div className="mb-4 flex items-center gap-3">
                  <div className="rounded-md border border-zinc-800 bg-zinc-950 p-2 text-zinc-200">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="font-semibold text-white">{layer.title}</h3>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {layer.modules.map((module) => (
                    <div
                      key={module}
                      className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-400"
                    >
                      {module}
                    </div>
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      <section className="flex flex-col gap-6">
        <SectionHeader
          eyebrow="Architecture from Eraser"
          title="4. Learning and Evaluation Pipeline"
          description="This workflow tracks the project from experiment configuration through policy training, baseline evaluation, analysis, and dashboard presentation."
        />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          {pipelineStages.map((stage, index) => (
            <div
              key={stage.title}
              className="rounded-xl border border-zinc-800 bg-black p-5"
            >
              <div className="mb-4 flex items-center justify-between">
                <span className="text-xs uppercase tracking-widest text-zinc-500">
                  Phase {index + 1}
                </span>
                <Workflow className="h-4 w-4 text-zinc-500" />
              </div>
              <h3 className="text-base font-semibold text-white">
                {stage.title}
              </h3>
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                {stage.detail}
              </p>
              <div className="mt-4 space-y-2">
                {stage.outputs.map((output) => (
                  <div
                    key={output}
                    className="rounded-md bg-zinc-900 px-3 py-2 text-xs text-zinc-400"
                  >
                    {output}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="rounded-xl border-zinc-800 bg-black p-6">
          <div className="mb-5 flex items-center gap-3">
            <Layers3 className="h-5 w-5 text-zinc-300" />
            <h2 className="text-xl font-bold text-white">Technology Stack</h2>
          </div>
          <div className="space-y-3">
            {stack.map(([layer, tech]) => (
              <div
                key={layer}
                className="grid grid-cols-1 gap-2 border-b border-zinc-900 pb-3 last:border-0 md:grid-cols-[120px_1fr]"
              >
                <span className="text-xs uppercase tracking-widest text-zinc-500">
                  {layer}
                </span>
                <span className="text-sm leading-6 text-zinc-300">{tech}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="rounded-xl border-zinc-800 bg-black p-6">
          <div className="mb-5 flex items-center gap-3">
            <Activity className="h-5 w-5 text-zinc-300" />
            <h2 className="text-xl font-bold text-white">
              Experiment Constants
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {[
              ["OpenGym port", "5555"],
              ["Step interval", "0.1 s"],
              ["Bottleneck", "2 Mbps / 10 ms"],
              ["Access links", "10 Mbps / 20 ms"],
              ["Default duration", "10 s"],
              ["MTU", "400 bytes"],
              ["TCP buffers", "4 MB"],
              ["DQN actions", "keep, +1500, -150, +4000"],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-lg border border-zinc-800 bg-zinc-950 p-4"
              >
                <p className="text-xs uppercase tracking-widest text-zinc-500">
                  {label}
                </p>
                <p className="mt-2 text-sm font-semibold text-white">{value}</p>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section className="flex flex-col gap-6">
        <SectionHeader
          eyebrow="Project ownership"
          title="Member Contributions"
          description="Names are shown as people, not duplicated usernames. The mapping is based on the commit history and contributor mapping supplied in the prompt."
        />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {contributions.map((item) => (
            <Card
              key={item.name}
              className="rounded-xl border-zinc-800 bg-black p-5"
            >
              <p className="text-lg font-semibold text-white">{item.name}</p>
              <p className="mt-1 text-xs uppercase tracking-widest text-zinc-500">
                {item.focus}
              </p>
              <p className="mt-4 text-sm leading-6 text-zinc-400">
                {item.delivery}
              </p>
            </Card>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_0.9fr]">
        <Card className="rounded-xl border-zinc-800 bg-black p-6">
          <div className="mb-5 flex items-center gap-3">
            <BarChart3 className="h-5 w-5 text-zinc-300" />
            <h2 className="text-xl font-bold text-white">
              Results Interpretation
            </h2>
          </div>
          <p className="text-sm leading-7 text-zinc-400">
            The included result files show DRL-TCP achieving higher average
            throughput, lower average RTT, and fewer packet losses than Cubic
            and NewReno in this project setup. The referenced arXiv work reports
            the same direction of improvement: a DQN-based TCP controller can
            maintain comparable throughput while reducing queueing delay
            relative to standard loss-based algorithms.
          </p>
          <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
            {[
              ["DRL-TCP", "9.498 Mbps", "14.844 ms", "76 loss"],
              ["Cubic", "8.051 Mbps", "30.155 ms", "252 loss"],
              ["NewReno", "7.514 Mbps", "35.208 ms", "355 loss"],
            ].map(([algo, throughput, rtt, loss]) => (
              <div
                key={algo}
                className="rounded-lg border border-zinc-800 bg-zinc-950 p-4"
              >
                <p className="font-semibold text-white">{algo}</p>
                <p className="mt-2 text-xs text-zinc-400">{throughput}</p>
                <p className="text-xs text-zinc-400">{rtt}</p>
                <p className="text-xs text-zinc-400">{loss}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card className="rounded-xl border-zinc-800 bg-black p-6">
          <div className="mb-5 flex items-center gap-3">
            <RadioTower className="h-5 w-5 text-zinc-300" />
            <h2 className="text-xl font-bold text-white">Limitations</h2>
          </div>
          <div className="space-y-3">
            {limitations.map((item) => (
              <div
                key={item}
                className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm leading-6 text-zinc-400"
              >
                {item}
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section className="rounded-xl border border-zinc-800 bg-black p-6">
        <h2 className="text-xl font-bold text-white">References</h2>
        <div className="mt-4 grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
          <a
            className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-zinc-300 transition-colors hover:text-white"
            href="https://arxiv.org/html/2508.01047v3"
            target="_blank"
            rel="noreferrer"
          >
            A Deep Reinforcement Learning-Based TCP Congestion Control
            Algorithm: Design, Simulation, and Evaluation
          </a>
          <a
            className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-zinc-300 transition-colors hover:text-white"
            href="https://app.eraser.io/workspace/zOV3c2oGyuDJJGuhXldf"
            target="_blank"
            rel="noreferrer"
          >
            Supplied Eraser architecture workspace
          </a>
          <a
            className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-zinc-300 transition-colors hover:text-white"
            href="https://www.nsnam.org/"
            target="_blank"
            rel="noreferrer"
          >
            NS-3 network simulator
          </a>
          <a
            className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-zinc-300 transition-colors hover:text-white"
            href="https://github.com/tkn-tub/ns3-gym"
            target="_blank"
            rel="noreferrer"
          >
            ns3-gym OpenGym interface
          </a>
        </div>
      </section>
    </main>
  );
}
