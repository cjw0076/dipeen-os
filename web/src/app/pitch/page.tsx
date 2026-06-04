"use client";

import { useState, type CSSProperties } from "react";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import styles from "./pitch.module.css";

type FlowStep = {
  title: string;
  body: string;
  icon: BrandIconName;
};

const providers = [
  "Claude",
  "Codex",
  "GPT",
  "Gemini",
  "Cursor",
  "Slack",
  "GitHub",
  "Browser",
  "Figma",
  "Drive",
  "Notion",
  "Jira",
];

const stackRows = [
  ["Agent Layer", "팀 목표 수행, 업무 특화 자동화, 외부 에이전트"],
  ["Orchestration", "계획 수립, 작업 분해, 실행 제어, 결과 검증"],
  ["Tools & API", "검색, 코드 실행, 데이터 분석, 외부 API"],
  ["Data Layer", "문서, 업무 데이터, 지식 베이스, 실시간 정보"],
  ["Infra Layer", "LLM, 임베딩, 컴퓨팅, 보안 네트워크"],
];

const demoSteps: FlowStep[] = [
  {
    title: "아이디어 입력",
    body: "사람이 목표를 입력하면 Dipeen이 작업으로 분해합니다.",
    icon: "meeting",
  },
  {
    title: "작업 할당",
    body: "각 에이전트가 capability 기준으로 작업을 임대합니다.",
    icon: "command",
  },
  {
    title: "로컬 실행",
    body: "워커는 각자의 환경에서 CLI, IDE, 도구를 사용합니다.",
    icon: "code",
  },
  {
    title: "증거 제출",
    body: "완료를 주장하려면 테스트, diff, 로그가 필요합니다.",
    icon: "review",
  },
  {
    title: "기억 승격",
    body: "검증된 결과는 팀의 재사용 가능한 지식으로 남습니다.",
    icon: "database",
  },
];

const values: Array<{ title: string; body: string; icon: BrandIconName }> = [
  {
    title: "신뢰 가능한 실행",
    body: "권한 기반 실행과 검증. 승인 없는 위험 작업은 없습니다.",
    icon: "shield",
  },
  {
    title: "팀 생산성 향상",
    body: "에이전트 팀의 협업을 가속하고 반복 작업을 자동화합니다.",
    icon: "meeting",
  },
  {
    title: "지식과 맥락 보존",
    body: "대화, 코드, 아티팩트, 결정을 검색 가능한 기억으로 남깁니다.",
    icon: "database",
  },
  {
    title: "운영 효율과 거버넌스",
    body: "현황 가시성과 리스크 통제로 조직 단위 확장을 준비합니다.",
    icon: "graph",
  },
];

const useCases: Array<{ title: string; body: string; icon: BrandIconName }> = [
  {
    title: "소프트웨어 개발",
    body: "코드 작성부터 리뷰, 테스트, 배포까지 개발 전 과정을 가속화",
    icon: "code",
  },
  {
    title: "데이터 · 분석",
    body: "데이터 수집, 정제, 분석, 리포트 생성을 한 번에 자동화",
    icon: "graph",
  },
  {
    title: "마케팅 · 콘텐츠",
    body: "아이디어 발굴부터 콘텐츠 제작, 성과 분석까지 통합 운영",
    icon: "spark",
  },
  {
    title: "운영 · 지원",
    body: "요청 처리, 문서 관리, 지식 검색을 자동화해 운영 효율 극대화",
    icon: "settings",
  },
];

const roadmap = [
  {
    title: "Alpha",
    body: "로컬 컨트롤 타워, Claude/Codex 워커, Dry-run 권한 레저",
    icon: "board" as BrandIconName,
  },
  {
    title: "Next",
    body: "OMO/Hermes lifecycle, 원격 워커 안전성, portable task bundle",
    icon: "workflow" as BrandIconName,
  },
  {
    title: "Scale",
    body: "Verifier 생태계, 팀 메모리 거버넌스, 조직 단위 Agent Office",
    icon: "graph" as BrandIconName,
  },
];

function DipeenLogo({ serif = false }: { serif?: boolean }) {
  return (
    <div className={serif ? styles.serifLogo : styles.logo}>
      <span className={styles.logoGlyph}>D</span>
      <span>Dipeen</span>
    </div>
  );
}

function SlideBadge({ n }: { n: string }) {
  return <span className={styles.slideBadge}>{n}</span>;
}

function IconOrb({
  icon,
  label,
  large = false,
}: {
  icon: BrandIconName;
  label?: string;
  large?: boolean;
}) {
  return (
    <div className={large ? styles.iconOrbLarge : styles.iconOrb}>
      <BrandIcon name={icon} size={large ? 54 : 30} />
      {label ? <span>{label}</span> : null}
    </div>
  );
}

function SlideShell({
  id,
  n,
  children,
  className = "",
  serifLogo = false,
}: {
  id?: string;
  n: string;
  children: React.ReactNode;
  className?: string;
  serifLogo?: boolean;
}) {
  return (
    <section className={`${styles.slide} ${className}`} id={id}>
      <div className={styles.paper}>
        <SlideBadge n={n} />
        <DipeenLogo serif={serifLogo} />
        {children}
      </div>
    </section>
  );
}

function OrbitGraphic() {
  const nodes = [
    ["Human", "meeting", "50%", "0%"],
    ["Claude", "agent", "90%", "29%"],
    ["Codex", "code", "82%", "73%"],
    ["Hermes", "workflow", "48%", "90%"],
    ["OMO", "command", "12%", "72%"],
    ["Local Tools", "settings", "10%", "31%"],
  ] as const;

  return (
    <div className={styles.orbitGraphic}>
      <div className={styles.orbitRing} />
      <div className={styles.orbitRingInner} />
      <div className={styles.orbitCore}>
        <span>D</span>
      </div>
      {nodes.map(([label, icon, left, top]) => (
        <div className={styles.orbitNode} key={label} style={{ left, top }}>
          <BrandIcon name={icon} size={24} />
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

function TerminalCard() {
  return (
    <div className={styles.terminalCard}>
      <div className={styles.terminalBar}>
        <span />
        <span />
        <span />
        <strong>Worker: Codex</strong>
      </div>
      <pre>{`$ pytest tests/test_onboarding.py
23 passed in 1.42s

$ git diff
+ support_levels: honest
+ permission_gate: dry_run
+ evidence: attached`}</pre>
    </div>
  );
}

function MiniDashboard() {
  return (
    <div className={styles.miniDashboard}>
      <div className={styles.dashTop}>
        <strong>Dipeen HQ</strong>
        <span>All systems normal</span>
      </div>
      <div className={styles.metricGrid}>
        {[
          ["Runs", "28", "6 running"],
          ["Success", "92%", "up 8%"],
          ["Agents", "18/24", "healthy"],
          ["Permissions", "3", "pending"],
        ].map(([label, value, sub]) => (
          <div className={styles.metricCard} key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <em>{sub}</em>
          </div>
        ))}
      </div>
      <div className={styles.dashBody}>
        <div>
          <h4>Recent runs</h4>
          {["Implement grid", "Payment flow", "Rate limit test"].map((row, i) => (
            <p key={row}>
              <BrandIcon name={i === 2 ? "check" : "agent"} size={15} />
              <span>{row}</span>
              <em>{i === 0 ? "Running" : "Verified"}</em>
            </p>
          ))}
        </div>
        <div>
          <h4>Evidence graph</h4>
          <div className={styles.evidenceGraph}>
            <span>PR #128</span>
            <span>Tests</span>
            <strong>R-020</strong>
            <span>Logs</span>
            <span>Approval</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PitchPage() {
  const [activeStep, setActiveStep] = useState(2);

  return (
    <main className={styles.deck}>
      <nav className={styles.nav}>
        <a href="#hero">Dipeen OS</a>
        <a href="#thesis">Thesis</a>
        <a href="#flow">Demo</a>
        <a href="#roadmap">Roadmap</a>
      </nav>

      <SlideShell id="hero" n="01">
        <div className={styles.heroGrid}>
          <div className={styles.heroCopy}>
            <DipeenLogo />
            <h1>Dipeen OS</h1>
            <p className={styles.heroLead}>Put your agents in one room.</p>
            <p className={styles.heroBody}>
              The open-source Agentic Slack and control plane for distributed AI
              agent teams. Coordinate. Verify. Govern. Remember.
            </p>
            <div className={styles.promiseRow}>
              {[
                ["Evidence First", "shield"],
                ["Permission Gated", "key"],
                ["Team Memory", "database"],
                ["Distributed by Design", "workflow"],
              ].map(([label, icon]) => (
                <span key={label}>
                  <BrandIcon name={icon as BrandIconName} size={24} />
                  {label}
                </span>
              ))}
            </div>
          </div>
          <OrbitGraphic />
        </div>
        <div className={styles.bottomLine}>
          Agents do the work. <span /> Dipeen makes the work accountable.
        </div>
      </SlideShell>

      <SlideShell id="thesis" n="02">
        <div className={styles.centerTitle}>
          <h2>The One-Line Thesis</h2>
          <p>
            AI agents can now work.
            <br />
            But teams <em>cannot yet</em> manage them.
          </p>
          <small>Multiple agents. Multiple tools. No shared control.</small>
        </div>
        <div className={styles.providerScreens}>
          {providers.slice(0, 8).map((provider, index) => (
            <article className={styles.providerScreen} key={provider}>
              <strong>{provider}</strong>
              <div className={index < 5 ? styles.darkScreen : styles.lightScreen}>
                <span />
                <span />
                <span />
                <span />
              </div>
            </article>
          ))}
        </div>
        <div className={styles.warningBand}>
          <BrandIcon name="review" size={52} />
          <p>
            <strong>This is not a team.</strong>
            <em>This is chaos with intelligence.</em>
          </p>
        </div>
      </SlideShell>

      <SlideShell n="03">
        <div className={styles.slideHeaderWide}>
          <h2>AI의 진화: 우리는 어디까지 왔는가</h2>
          <p>모델 → 도구 사용 → 기억과 기술 → 운영과 거버넌스</p>
        </div>
        <div className={styles.timeline}>
          {[
            ["01", "트랜스포머 시대", "~2017", "모델이 맥락을 학습"],
            ["02", "챗봇 시대", "2018 ~ 2022", "AI는 답한다"],
            ["03", "IDE 시대", "2022 ~ 2023", "AI는 코드를 편집한다"],
            ["04", "에이전트 시대", "2024 ~", "AI는 실행하고 증거를 남긴다"],
          ].map(([n, title, year, body], index) => (
            <article className={index === 3 ? styles.timelineActive : ""} key={title}>
              <span>{n}</span>
              <h3>{title}</h3>
              <small>{year}</small>
              <IconOrb icon={index === 0 ? "layers" : index === 1 ? "chat" : index === 2 ? "code" : "agent"} large />
              <p>{body}</p>
            </article>
          ))}
        </div>
        <div className={styles.insightBand}>
          이제 필요한 것은 더 똑똑한 모델이 아니라, 신뢰할 수 있는 운영 및
          거버넌스 레이어입니다.
        </div>
      </SlideShell>

      <SlideShell n="04">
        <div className={styles.compareTitle}>
          <h2>LLM vs Agent: 질문에 답하는 시대는 끝났습니다</h2>
          <p>이제는 스스로 판단하고, 도구를 사용해, 결과를 만들어내는 Agent의 시대입니다.</p>
        </div>
        <div className={styles.compareGrid}>
          <article>
            <h3>LLM (언어 모델)</h3>
            <div className={styles.chatBubble}>이번 달 매출 리포트 정리해줘.</div>
            <div className={styles.chatBubbleMuted}>
              텍스트 답변은 가능하지만 외부 시스템과 상호작용하지 않습니다.
            </div>
            {["대화 기반", "지식 기반", "도구 미사용", "수동적 결과"].map((item) => (
              <p key={item}>
                <BrandIcon name="chat" size={22} />
                {item}
              </p>
            ))}
          </article>
          <span className={styles.vsBadge}>VS</span>
          <article className={styles.agentPanel}>
            <h3>Agent (지능형 수행자)</h3>
            <div className={styles.agentFlow}>
              {["의도 이해", "계획 수립", "도구 사용", "결과 생성", "보고 완료"].map((item, i) => (
                <span key={item}>
                  <BrandIcon name={i === 0 ? "inspect" : i === 1 ? "board" : i === 2 ? "settings" : i === 3 ? "review" : "check"} size={24} />
                  {item}
                </span>
              ))}
            </div>
            {["목표 기반", "행동 기반", "도구 활용", "검증된 결과"].map((item) => (
              <p key={item}>
                <BrandIcon name="workflow" size={22} />
                {item}
              </p>
            ))}
          </article>
        </div>
        <div className={styles.insightBand}>
          LLM은 무엇을 아는가에 강하고, Agent는 무엇을 해내는가에 강합니다.
        </div>
      </SlideShell>

      <SlideShell n="05">
        <div className={styles.slideHeaderWide}>
          <h2>Agent Stack: 에이전트는 계층 위에서 작동합니다</h2>
          <p>복잡한 업무는 다양한 도구와 시스템의 계층 위에서 이루어집니다.</p>
        </div>
        <div className={styles.stackRows}>
          {stackRows.map(([title, body], i) => (
            <div className={styles.stackRow} key={title}>
              <span>{5 - i}</span>
              <IconOrb icon={["agent", "workflow", "settings", "database", "layers"][i] as BrandIconName} />
              <strong>{title}</strong>
              <p>{body}</p>
            </div>
          ))}
          <aside className={styles.stackReasons}>
            {["책임의 분리", "교체 가능성", "보안과 통제", "지속적 개선"].map((item, i) => (
              <article key={item}>
                <BrandIcon name={["shield", "settings", "key", "graph"][i] as BrandIconName} size={28} />
                <strong>{item}</strong>
              </article>
            ))}
          </aside>
        </div>
        <div className={styles.insightBand}>
          에이전트는 마법이 아닙니다. 견고한 계층 위에서 통제된 방식으로 작동할 때 신뢰할 수 있습니다.
        </div>
      </SlideShell>

      <SlideShell n="06" className={styles.assetSlide}>
        <div className={styles.fragmentedGrid}>
          <div>
            <h2>단절된 도구들, 파편화된 업무</h2>
            <p>각 도구는 잘 작동합니다. 하지만 서로 연결되지 않습니다.</p>
            <ul>
              {["컨텍스트 손실", "수작업 전달", "상태 불일치", "책임 불명확", "생산성 저하"].map((item) => (
                <li key={item}>
                  <BrandIcon name="review" size={20} />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className={styles.toolCloud}>
            {providers.slice(0, 9).map((provider, i) => (
              <span key={provider} style={{ "--i": i } as CSSProperties}>
                {provider}
              </span>
            ))}
          </div>
          <img className={styles.officeAsset} src="/pitch-assets/desk-prop-preview.png" alt="Dipeen desk prop" />
        </div>
      </SlideShell>

      <SlideShell n="07" className={styles.officeSlide}>
        <div className={styles.officeBackdrop}>
          <img src="/pitch-assets/office-scene-preview.png" alt="Dipeen 3D office scene" />
        </div>
        <div className={styles.officeText}>
          <h2>네트워크 인프라: 연결은 단순하게, 신뢰는 강하게</h2>
          <p>HQ는 제어하고, 워커는 아웃바운드로 당겨갑니다.</p>
          <div className={styles.officePrinciples}>
            {["아웃바운드 우선", "키는 로컬에", "최소 권한 통신", "모든 변경 기록"].map((item, i) => (
              <span key={item}>
                <BrandIcon name={["shield", "key", "inspect", "database"][i] as BrandIconName} size={25} />
                {item}
              </span>
            ))}
          </div>
        </div>
      </SlideShell>

      <SlideShell id="flow" n="08">
        <div className={styles.slideHeaderWide}>
          <h2>데모 플로우: 신뢰가 만들어지는 순간</h2>
          <p>idea가 들어와 작업으로 분해되고, 실행되며, 증거로 검증되고, 기억으로 승격됩니다.</p>
        </div>
        <div className={styles.demoFlow}>
          {demoSteps.map((step, i) => (
            <button
              className={activeStep === i ? styles.demoActive : ""}
              key={step.title}
              onClick={() => setActiveStep(i)}
              type="button"
            >
              <span>{i + 1}</span>
              <BrandIcon name={step.icon} size={30} />
              <strong>{step.title}</strong>
              <small>{step.body}</small>
            </button>
          ))}
        </div>
        <div className={styles.demoConsoleGrid}>
          <TerminalCard />
          <div className={styles.memoryQueue}>
            <h3>메모리 큐</h3>
            {["온보딩 가이드 v2", "지원 레벨 정의", "테스트 패턴"].map((item) => (
              <p key={item}>
                <BrandIcon name="review" size={18} />
                {item}
                <span>PROMOTE</span>
              </p>
            ))}
          </div>
        </div>
      </SlideShell>

      <SlideShell n="09">
        <div className={styles.whyGrid}>
          <div>
            <h2>공급자 폭발</h2>
            <p className={styles.bigLine}>미래는 이중적입니다.</p>
            <p>모델, 도구, 환경, 배포 방식이 제각각입니다. 다양성은 inevitability이지만, 복잡성과 리스크도 함께 만듭니다.</p>
          </div>
          <div className={styles.ecosystemGrid}>
            {providers.concat(["Llama", "Mistral", "Ollama", "OpenCode", "Hermes", "Custom"]).map((p, i) => (
              <article key={`${p}-${i}`}>
                <BrandIcon name={i % 4 === 0 ? "agent" : i % 4 === 1 ? "code" : i % 4 === 2 ? "layers" : "workflow"} size={24} />
                <strong>{p}</strong>
                <span>{i < 4 ? "Cloud" : i < 8 ? "Runtime" : "Local"}</span>
              </article>
            ))}
          </div>
        </div>
        <div className={styles.insightBand}>
          Dipeen은 이 복잡한 생태계를 하나의 팀으로 묶어 줍니다.
        </div>
      </SlideShell>

      <SlideShell n="10">
        <div className={styles.slideHeaderWide}>
          <h2>Why Dipeen</h2>
          <p>Dipeen은 모델이 아니라, 팀이 신뢰하고 운영할 수 있는 실행 계층입니다.</p>
        </div>
        <div className={styles.valueCards}>
          {values.map((value, i) => (
            <article key={value.title}>
              <span>0{i + 1}</span>
              <IconOrb icon={value.icon} large />
              <h3>{value.title}</h3>
              <p>{value.body}</p>
            </article>
          ))}
        </div>
        <div className={styles.darkQuote}>
          Dipeen은 자동화를 넘어서, 신뢰할 수 있는 성과를 만드는 운영 계층입니다.
        </div>
      </SlideShell>

      <SlideShell n="11">
        <div className={styles.architectureGrid}>
          <div>
            <h2>Dipeen OS의 아키텍처</h2>
            <p>본사는 통제하고, 워커는 실행하며, 모든 증거는 Dipeen으로 올라옵니다.</p>
            {["HQ (본사)", "API 계층", "Dipeen Core", "NAT & Worker Layer"].map((item, i) => (
              <article className={styles.layerCard} key={item}>
                <BrandIcon name={["board", "workflow", "database", "agent"][i] as BrandIconName} size={38} />
                <div>
                  <strong>{i + 1}. {item}</strong>
                  <span>
                    {i === 0
                      ? "Web UI / Dashboard"
                      : i === 1
                        ? "REST API / WebSocket"
                        : i === 2
                          ? "Command queue, policy, memory"
                          : "Local provider runtime"}
                  </span>
                </div>
              </article>
            ))}
          </div>
          <MiniDashboard />
        </div>
      </SlideShell>

      <SlideShell n="12">
        <div className={styles.evidenceCompare}>
          <h2>Evidence First: 증거 없이는 완료가 아닙니다</h2>
          <div>
            <article>
              <BrandIcon name="review" size={42} />
              <h3>잘못된 완료</h3>
              <p>에이전트가 “Done”이라고 보고</p>
              <ul>
                <li>결과 파일 없음</li>
                <li>검증 불가</li>
                <li>다시 작업 필요</li>
              </ul>
            </article>
            <span className={styles.bigArrow}>→</span>
            <article className={styles.verifiedCard}>
              <BrandIcon name="check" size={42} />
              <h3>올바른 완료</h3>
              <p>검증 가능한 증거로 확인</p>
              <ul>
                <li>코드 패치 생성됨</li>
                <li>테스트 통과</li>
                <li>문서 업데이트됨</li>
                <li>PR 생성됨</li>
              </ul>
            </article>
          </div>
        </div>
      </SlideShell>

      <SlideShell n="13">
        <div className={styles.loopSlide}>
          <h2>검증 가능한 실행 루프</h2>
          <p>계획부터 검증까지, 모든 단계가 증거로 남습니다.</p>
          <div className={styles.loopSteps}>
            {["계획", "실행", "검증", "완료"].map((item, i) => (
              <article key={item}>
                <span>0{i + 1}</span>
                <IconOrb icon={["board", "agent", "review", "shield"][i] as BrandIconName} large />
                <h3>{item}</h3>
                <p>{["목표와 작업 정의", "에이전트가 작업 수행", "결과와 증거 자동 수집", "검증된 결과로 합의"][i]}</p>
              </article>
            ))}
          </div>
        </div>
      </SlideShell>

      <SlideShell n="14">
        <div className={styles.permissionSlide}>
          <h2>Permission Gate: 승인 없는 실행은 없습니다</h2>
          <p>위험한 작업은 자동으로 멈추고, 승인 요청 → 검토 → 승인 후 실행 순서로 진행됩니다.</p>
          <div className={styles.permissionSteps}>
            {["Agent 요청", "Permission Request", "Human Review", "Approved Execution"].map((item, i) => (
              <article key={item}>
                <span>{String(i + 1).padStart(2, "0")}</span>
                <IconOrb icon={["agent", "review", "meeting", "shield"][i] as BrandIconName} large />
                <h3>{item}</h3>
              </article>
            ))}
          </div>
        </div>
        <div className={styles.insightBand}>자동화는 강력해야 하지만, 통제는 더 강해야 합니다.</div>
      </SlideShell>

      <SlideShell n="15">
        <div className={styles.beforeAfter}>
          <h2>Dipeen OS가 팀을 더 강하게 만듭니다</h2>
          <div>
            <article>
              <h3>Before</h3>
              {["대화와 문서가 흩어져 맥락을 잃기 쉽습니다.", "결과와 버전이 분산되어 찾기 어렵습니다.", "승인과 검토가 수동이라 시간이 오래 걸립니다.", "실행과 증거가 연결되지 않아 신뢰하기 어렵습니다."].map((item) => (
                <p key={item}>{item}</p>
              ))}
            </article>
            <span>→</span>
            <article className={styles.afterPanel}>
              <h3>With Dipeen OS</h3>
              {["모든 대화와 결정이 한곳에 모여 맥락을 유지합니다.", "결과, 버전, 아티팩트가 정리되어 쉽게 찾고 재사용합니다.", "승인과 검토가 자동화되어 빠르고 일관되게 진행됩니다.", "모든 실행이 증거로 남아 신뢰할 수 있는 결과를 만듭니다."].map((item) => (
                <p key={item}>{item}</p>
              ))}
            </article>
          </div>
        </div>
      </SlideShell>

      <SlideShell n="16">
        <div className={styles.useCaseSlide}>
          <h2>Dipeen OS의 활용 사례</h2>
          <p>다양한 팀이 Dipeen OS로 더 빠르고, 더 안전하게, 더 신뢰할 수 있는 결과를 만듭니다.</p>
          <div className={styles.useCaseGrid}>
            {useCases.map((useCase) => (
              <article key={useCase.title}>
                <IconOrb icon={useCase.icon} large />
                <h3>{useCase.title}</h3>
                <p>{useCase.body}</p>
              </article>
            ))}
          </div>
          <img src="/pitch-assets/character-kit-preview.png" alt="Dipeen agent character kit" />
        </div>
      </SlideShell>

      <SlideShell n="17" className={styles.characterSlide}>
        <div className={styles.characterCopy}>
          <h2>함께 Agent Control Plane을 만듭시다</h2>
          <p>Dipeen은 흩어진 에이전트를 신뢰 가능한 팀으로 만드는 운영 계층입니다.</p>
        </div>
        <div className={styles.characterRow}>
          {[
            ["/pitch-assets/human-manager.png", "사용자"],
            ["/pitch-assets/fe-agent.png", "기여자"],
            ["/pitch-assets/qa-agent.png", "검증자"],
            ["/pitch-assets/be-agent.png", "운영자"],
          ].map(([src, label]) => (
            <article key={label}>
              <img src={src} alt={`${label} character`} />
              <strong>{label}</strong>
            </article>
          ))}
        </div>
        <div className={styles.ctaBand}>
          우리가 원하는 것은 더 많은 자동화가 아니라, 믿고 운영할 수 있는 Agent 팀입니다.
        </div>
      </SlideShell>

      <SlideShell id="roadmap" n="18" serifLogo>
        <div className={styles.roadmapSlide}>
          <h2>로드맵: 작은 팀에서 조직 전체로</h2>
          <p>Dipeen은 로컬 알파에서 시작해, 안전한 원격 워커와 검증 생태계로 확장됩니다.</p>
          <div className={styles.roadmapCards}>
            {roadmap.map((phase, i) => (
              <article key={phase.title}>
                <span>{i + 1}</span>
                <h3>{phase.title}</h3>
                <BrandIcon name={phase.icon} size={70} />
                <p>{phase.body}</p>
              </article>
            ))}
          </div>
          <div className={styles.insightBand}>
            목표는 더 많은 에이전트를 붙이는 것이 아니라, 팀이 믿고 운영할 수 있는 실행 체계를 만드는 것입니다.
          </div>
        </div>
      </SlideShell>

      <SlideShell n="19" className={styles.finalSlide} serifLogo>
        <div className={styles.finalGrid}>
          <div>
            <h2>다음 AI 제품은 챗봇이 아닙니다.</h2>
            <p>사람과 에이전트가 함께 일하는 새로운 작업 공간입니다.</p>
            <strong>Dipeen이 그 공간입니다.</strong>
          </div>
          <OrbitGraphic />
        </div>
        <div className={styles.finalFooter}>
          Agents do the work. <span /> Dipeen makes the work accountable.
        </div>
      </SlideShell>
    </main>
  );
}
