import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import {
  BlockerItem,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CompactTable,
  CompactTableCell,
  CompactTableHeader,
  CompactTableRow,
  RemediationLadder,
  StatusBadge
} from ".";

export function run() {
  rendersStatusBadgeLabelsAndClasses();
  rendersCardSectionsWithoutHoverWhenDisabled();
  rendersCompactTableHeadersAsHeaderCells();
  rendersRemediationLadderNextStepWithoutBrowserState();
  rendersBlockerActionOnlyWhenActionIsComplete();
}

function rendersStatusBadgeLabelsAndClasses() {
  const html = renderToStaticMarkup(<StatusBadge status="needs-attention" />);

  assert.match(html, /ui-status-badge-needs-attention/);
  assert.match(html, />Needs attention</);
}

function rendersCardSectionsWithoutHoverWhenDisabled() {
  const html = renderToStaticMarkup(
    <Card hover={false} className="custom-card">
      <CardHeader>Header</CardHeader>
      <CardContent>Content</CardContent>
      <CardFooter>Footer</CardFooter>
    </Card>
  );

  assert.match(html, /ui-card custom-card/);
  assert.doesNotMatch(html, /ui-card-hover/);
  assert.match(html, /ui-card-header/);
  assert.match(html, /ui-card-content/);
  assert.match(html, /ui-card-footer/);
}

function rendersCompactTableHeadersAsHeaderCells() {
  const html = renderToStaticMarkup(
    <CompactTable>
      <CompactTableHeader>
        <CompactTableCell>Device</CompactTableCell>
        <CompactTableCell align="right">Status</CompactTableCell>
      </CompactTableHeader>
      <tbody>
        <CompactTableRow hover={false}>
          <CompactTableCell>NetApp</CompactTableCell>
          <CompactTableCell align="right">Ready</CompactTableCell>
        </CompactTableRow>
      </tbody>
    </CompactTable>
  );

  assert.match(html, /<th class="ui-compact-table-cell ui-compact-table-cell-left">Device<\/th>/);
  assert.match(html, /<th class="ui-compact-table-cell ui-compact-table-cell-right">Status<\/th>/);
  assert.doesNotMatch(html, /ui-compact-table-row-hover/);
}

function rendersRemediationLadderNextStepWithoutBrowserState() {
  const html = renderToStaticMarkup(
    <RemediationLadder
      defaultOpen
      status="blocked"
      statusLabel="Blocked"
      summary="Two checks remain"
      title="Setup ladder"
      steps={[
        {
          detail: "Console access confirmed",
          label: "Console",
          nextAction: "Continue",
          status: "ready"
        },
        {
          detail: "RAID plan missing",
          label: "RAID",
          nextAction: "Create the RAID plan",
          status: "blocked"
        }
      ]}
    />
  );

  assert.match(html, /<details class="ui-remediation-ladder ui-remediation-ladder-standard" open="">/);
  assert.match(html, /<span>Next<\/span>/);
  assert.match(html, /<strong>RAID<\/strong>/);
  assert.match(html, /Create the RAID plan/);
}

function rendersBlockerActionOnlyWhenActionIsComplete() {
  const withoutAction = renderToStaticMarkup(
    <BlockerItem severity="warning" code="SUBNET_MISMATCH" message="Saved subnet does not match host." actionLabel="Fix" />
  );
  const withAction = renderToStaticMarkup(
    <BlockerItem
      severity="critical"
      code="CISCO_MISSING"
      message="Switch management is not configured."
      actionHref="/network"
      actionLabel="Go to Network"
    />
  );

  assert.doesNotMatch(withoutAction, /ui-blocker-action/);
  assert.match(withAction, /ui-blocker-item-critical/);
  assert.match(withAction, /href="\/network"/);
  assert.match(withAction, /Go to Network/);
}
