import type { Scenario } from "../types/config";
import type { MonteCarloResult } from "../types/result";
import { AttritionChart } from "./AttritionChart";
import { EngagementCanvas } from "./EngagementCanvas";
import { Headline } from "./Headline";
import { LeakerHistogram } from "./LeakerHistogram";
import { MagazineTimeline } from "./MagazineTimeline";
import { Panel } from "./Panel";

export function ScenarioView({
  mc,
  scenario,
  color,
}: {
  mc: MonteCarloResult;
  scenario: Scenario;
  color: string;
}) {
  return (
    <div className="scenario-view">
      <Headline mc={mc} />
      <Panel
        title="Engagement replay"
        hint={`representative run (seed ${mc.representative_seed}, the median-leaker outcome)`}
      >
        <EngagementCanvas trace={mc.representative} scenario={scenario} color={color} />
      </Panel>
      <div className="panel-grid">
        <Panel
          title="Leaker distribution"
          hint={`${mc.runs} runs - one run lies, the distribution tells the truth`}
        >
          <LeakerHistogram dist={mc.metrics.leakers_total} color={color} />
        </Panel>
        <Panel title="Attrition" hint="mean threats alive over time">
          <AttritionChart curve={mc.attrition_curve} color={color} />
        </Panel>
        <Panel title="Magazine timeline" hint="when each layer ran dry">
          <MagazineTimeline stats={mc.magazine_timeline} />
        </Panel>
      </div>
    </div>
  );
}
