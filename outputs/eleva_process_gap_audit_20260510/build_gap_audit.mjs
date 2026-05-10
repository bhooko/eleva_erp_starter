import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "C:/eleva_erp_starter/outputs/eleva_process_gap_audit_20260510";
const outputPath = `${outputDir}/eleva_erp_process_gap_audit_20260510.xlsx`;

const gaps = [
  ["G-001", "P0", "Sales / CRF", "CRF approval is required for Closed Won and Quote Submission, but the CRF detail screen is effectively read-only.", "app.py:23059, app.py:25613, app.py:25857, templates/sales/client_requirement_form_detail.html:22", "Sales can be blocked by a mandatory design confirmation flow that has no clear operational edit/approval route.", "Add controlled CRF sales/design edit and confirm actions with audit trail."],
  ["G-002", "P0", "Sales to Design", "Design tasks created from Sales lose their sales origin fields.", "app.py:8548, app.py:8583, app.py:25340, templates/partials/design_task_modal.html:57", "Opportunity detail searches for origin_type='sales', so sales-created design tasks can disappear from the opportunity handoff.", "Persist origin_type, origin_id, and origin_reference from the modal when creating design tasks."],
  ["G-003", "P1", "Sales to Projects", "Closed Won conversion creates Project rows only; it does not auto-create project tasks, design tasks, BOM workflow, or procurement handoff.", "app.py:25487, app.py:28835", "A won job can become a project shell with no execution workflow unless someone manually applies a template.", "Apply a default project template during conversion or force template selection before conversion completes."],
  ["G-004", "P1", "Projects", "Manual project task creation is QC-only even though templates support Design, SRT, QC, and general work.", "app.py:3191, app.py:28944, app.py:29030", "Project users cannot create ad hoc design/SRT/project-control tasks from the project screen.", "Extend manual task creation to choose module and create the correct linked record."],
  ["G-005", "P1", "Design / BOM", "Design status changes only validate the status name, not required workflow evidence.", "app.py:8629, app.py:8951", "Tasks can move to approval/BOM/final states without drawing approval, BOM readiness, or finalized package checks.", "Add transition guards for drawing upload, approval, BOM package finalization, and pending inputs."],
  ["G-006", "P1", "Sales / Design Visibility", "Opportunity open-design-task detection uses obsolete statuses.", "app.py:3241, app.py:25359", "Active design blockers may not show as open on the opportunity page.", "Update open status logic to match current design statuses."],
  ["G-007", "P1", "Sales Quotation", "Quotation is mostly file tracking; calculated opportunity value looks for quoted_value/value/amount fields that SalesOpportunityFile does not have.", "eleva_app/models.py:808, eleva_app/models.py:987", "Quotation amount, revision value, and conversion value can be missing or unreliable.", "Implement formal quotation rows/amount fields or connect quotation request items to final quote values."],
  ["G-008", "P1", "BOM to Purchase", "PO creation has inconsistent BOM linkage paths.", "app.py:11822, app.py:11838, app.py:13179, app.py:13420, app.py:9231", "POs generated from BOM can miss later BOM specification sync warnings.", "Make all PO creation paths populate source_bom_line_id, locked specification, and sync metadata consistently."],
  ["G-009", "P2", "Procurement Plan", "Procurement plan counts Draft POs as ordered/created.", "app.py:11001, app.py:11046, templates/bom_procurement_plan.html:23", "Procurement progress can be overstated before vendors receive/accept POs.", "Separate Draft, Issued, Closed, and Cancelled quantities in the procurement plan."],
  ["G-010", "P2", "Purchase Orders", "PO status can be manually changed to Issued, bypassing the send/issue route.", "app.py:12754, app.py:12778, app.py:12840, templates/purchase_order_detail.html:62", "Users can mark a PO as issued without email/acknowledgement/approval evidence.", "Restrict Issued transition to the send/issue action or record manual issue reason and acknowledgement."],
  ["G-011", "P1", "Stores / GRN", "Closed GRN can be reopened without reversing posted inventory.", "app.py:18113, app.py:18247", "Inventory can stay posted while the GRN returns to Open, creating accounting/stock reconciliation confusion.", "Block reopening after inventory posting or implement a reversal movement."],
  ["G-012", "P1", "Stores / Delivery", "Delivery Order confirmation warns on book-stock shortfall but still deducts stock.", "app.py:17851, app.py:17886", "Book stock can go negative and reservations can exceed available stock.", "Block confirmation on shortfall or require an override approval with explicit backorder status."],
  ["G-013", "P2", "Stores QC / QC", "Material QC in GRN creates VendorIssue records but not QCWork/Form/Submission records.", "eleva_app/models.py:3284, app.py:18022, app.py:18072, app.py:28087", "Material inspection and operational QC are separate processes, so QC reporting is incomplete.", "Bridge failed/inspection-required GRN lines to QCWork or clearly keep them as Stores-only QC with reporting."],
  ["G-014", "P1", "SARV / Customer Support", "SARV webhook logs calls and recordings only; it does not create a ticket, service task, or triage item.", "integrations/sarv/routes.py:33, app.py:4332, app.py:4379, app.py:30255", "Inbound calls can exist as call records without operational follow-up ownership.", "Create configurable call-to-ticket rules for missed/answered/sales/service call outcomes."],
  ["G-015", "P1", "Customer Support", "Customer Support tickets are JSON-state while most downstream modules are relational.", "app.py:3642, app.py:3671, app.py:4916, eleva_app/models.py:1374", "Ticket handoffs are weaker than Service/QC/SRT/Stores records and harder to audit/report.", "Move support tickets and linked tasks into SQL tables or add a sync table with immutable history."],
  ["G-016", "P1", "Support to Service", "Support-to-service creates a Lift service_schedule JSON entry, not a ServiceTask.", "app.py:31365, app.py:31439, app.py:32139, app.py:32202", "Service teams may not get a formal task with status, owner, proof, parts, and closure logic.", "Create ServiceTask records from service-related tickets and sync closure back to the ticket."],
  ["G-017", "P1", "Customer Support Closure", "Ticket closure rules ignore many downstream handoffs.", "app.py:3819, app.py:4998, tests/test_ticket_closure_rules.py:11", "Tickets can close while related sales/opportunity/downstream work remains open.", "Define which downstream task types must block ticket closure and show unresolved blockers."],
  ["G-018", "P1", "Service", "Service task media requirement and parts usage are not enforced into closure/inventory.", "eleva_app/models.py:1389, app.py:32081, app.py:32231, app.py:32254", "A task marked 'Photos mandatory' can close without proof; parts usage does not consume or reserve Stores stock.", "Enforce proof before closure and route parts usage through inventory/DO/DC or service stock ledger."],
  ["G-019", "P2", "Service Automations", "Service automations page renders configuration only; flows are not executable jobs/routes.", "app.py:3356, app.py:35371, templates/service/automations.html:1", "Users may assume reminders/escalations/stock deductions run when they are only displayed.", "Implement actual scheduled jobs or mark the page as configuration roadmap until enabled."],
  ["G-020", "P1", "QC", "QC submission/status flow has a status dead-end.", "app.py:28259, app.py:28357, app.py:36387", "Submissions move work to Inspection Done, but close is only allowed from Rectification Pending; all-OK and NG flows require manual correction.", "After submission, route all-OK to close-ready/closed and NG to Rectification Pending with evidence checks."],
  ["G-021", "P2", "SRT / QC", "SRT activity and site lists rely on in-memory structures and SRT completion does not release dependent QC work.", "app.py:3339, app.py:3731, app.py:3769, app.py:5470, app.py:35766", "Timeline/site data can be lost on restart and project dependencies do not fully control downstream QC.", "Persist SRT events/sites and wire SRT status completion into project/QC dependency release."],
  ["G-022", "P2", "Service Contracts", "Multi-lift contract data exists, but AMC fields are applied mainly through the first linked lift.", "eleva_app/models.py:1447, eleva_app/models.py:1485, app.py:34964, app.py:35034", "PM frequency and contract metadata may not propagate to every lift under a multi-lift contract.", "Apply contract schedule data per linked lift or store contract-level PM rules consumed by PM generation."],
  ["G-023", "P1", "Assets", "Quantity-based asset issue checks against master qty but movement creation does not reduce available qty or track split custody.", "app.py:16446, app.py:16666, eleva_app/models.py:3152", "The same quantity asset can be partially issued repeatedly and current custodian/location becomes inaccurate for split quantities.", "Add available/issued qty tracking or child lots for quantity-based assets."],
  ["G-024", "P2", "Assets", "AssetMovement supports reference_type/reference_id, but issue/return routes do not capture project/ticket/service references.", "eleva_app/models.py:3192, app.py:17196, app.py:17231", "Asset accountability is internal to Assets but not traceable to the job/ticket/task that caused movement.", "Add optional reference fields to issue/return forms and prefill them from project/service contexts."],
  ["G-025", "P2", "Cross-module Notifications", "Several handoff points have notification TODOs.", "app.py:13465, app.py:17900, app.py:18792", "Purchase/design/store handoffs rely on users checking screens manually.", "Create notifications for BOM-to-PO, DO confirmation, and DC delivery events."],
  ["G-026", "P2", "Project to Service Handover", "Closed-won/project conversion does not create Service customer/lift master records.", "app.py:25487, eleva_app/models.py:1420, eleva_app/models.py:1284", "After installation/project work, service lifecycle setup remains manual.", "Add commissioning/handover action that creates/links Customer, Lift, warranty, and AMC/PM setup."]
];

const businessGaps = [
  ["Accounting / Finance", "Purchase orders and operational stock exist.", "No full customer invoicing, receipts, collections, vendor bills, payments, GST/TDS, ledger, AR/AP, or P&L flow found.", "Phase later unless accounting integration is in scope."],
  ["Formal Quotation Builder", "Sales quotation requests and file uploads exist.", "No complete priced quotation document lifecycle with item pricing, revision comparison, approval, and acceptance.", "Implement before relying on opportunity values for campaign or sales performance."],
  ["HR / Payroll / Attendance", "Users and assignment exist.", "No employee attendance, payroll, leave, expense, or HR compliance module found.", "Separate HRMS integration or future module."],
  ["AMC Billing / Renewal Automation", "Service contracts and PM views exist.", "Billing, renewal reminders, collection tracking, and escalation are not fully implemented.", "Add after contracts are relationally solid across all linked lifts."],
  ["Commissioning / Handover", "Projects and Service customer/lift records exist separately.", "No formal handover from installation project to service/warranty/PM lifecycle.", "Treat as a critical bridge after project execution."],
  ["Approval / Authorization Matrix", "Some module visibility and admin checks exist.", "No consistent approval matrix for quote, PO issue, stock override, GRN reopening, decommission/lost asset, or service closure exceptions.", "Implement lightweight action approvals only at risky transitions."],
  ["Document Acceptance / E-sign", "Files can be uploaded.", "No customer/vendor acceptance tracking, e-signature, or formal acknowledgement workflow.", "Add when quotation/PO/customer contract process matures."],
  ["Mobile / Field App", "Web screens and QR-ready asset codes exist.", "No mobile-first field workflow, offline capture, QR scan issue/return, or technician app.", "Future phase; prioritize service/QC proof enforcement first."],
  ["Campaign ROI / Attribution", "Lead source exists and sales leads/opportunities exist.", "No ad spend import, campaign cost, attribution model, or lead-to-revenue funnel dashboard found.", "Add once lead qualification and quotation value are reliable."],
  ["Preventive Maintenance Scheduler", "PM/contract screens exist.", "Automation appears partial/static; actual scheduled job generation/escalation needs hard verification/implementation.", "Make scheduler explicit with generated ServiceTasks and due/overdue alerts."]
];

const priorityRank = { P0: 0, P1: 1, P2: 2, P3: 3 };
const priorityCounts = Object.fromEntries(["P0", "P1", "P2", "P3"].map((p) => [p, gaps.filter((g) => g[1] === p).length]));
const moduleCounts = [...new Set(gaps.map((g) => g[2]))]
  .map((m) => [m, gaps.filter((g) => g[2] === m).length])
  .sort((a, b) => b[1] - a[1]);

function styleHeader(range) {
  range.format = {
    fill: "#1F2937",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
}

function styleTitle(range) {
  range.format = {
    fill: "#111827",
    font: { bold: true, color: "#FFFFFF", size: 16 },
  };
}

function addTable(sheet, startCell, headers, rows, tableName) {
  const start = sheet.getRange(startCell);
  const data = [headers, ...rows];
  start.writeValues(data);
  const range = start.resize(data.length, headers.length);
  styleHeader(range.getRow(0));
  range.format.wrapText = true;
  const table = sheet.tables.add(range.address, true, tableName);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  return range;
}

await fs.mkdir(outputDir, { recursive: true });
const workbook = Workbook.create();

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;
summary.getRange("A1:H1").merge();
summary.getRange("A1").values = [["Eleva ERP Process Flow Gap Audit"]];
styleTitle(summary.getRange("A1:H1"));
summary.getRange("A2:H2").merge();
summary.getRange("A2").values = [["Read-only code-backed audit as of 2026-05-10. Evidence references are file paths and line numbers from the current checkout."]];
summary.getRange("A2:H2").format = { fill: "#E5E7EB", font: { color: "#111827" }, wrapText: true };
summary.getRange("A4:B9").values = [
  ["Total confirmed gaps", gaps.length],
  ["P0 blockers", priorityCounts.P0],
  ["P1 high risk", priorityCounts.P1],
  ["P2 medium", priorityCounts.P2],
  ["Business functions listed", businessGaps.length],
  ["Code changed", "No"],
];
summary.getRange("A4:A9").format = { font: { bold: true }, fill: "#F3F4F6" };
summary.getRange("D4:E7").values = [
  ["Priority", "Meaning"],
  ["P0", "Blocks or breaks a required process"],
  ["P1", "High operational/data integrity risk"],
  ["P2", "Important gap, manageable with manual workaround"],
];
styleHeader(summary.getRange("D4:E4"));
addTable(
  summary,
  "A12",
  ["ID", "Priority", "Module", "Gap", "Recommended next step"],
  gaps
    .sort((a, b) => priorityRank[a[1]] - priorityRank[b[1]])
    .slice(0, 12)
    .map((g) => [g[0], g[1], g[2], g[3], g[6]]),
  "TopGapsTable"
);
summary.getRange("A:A").format.columnWidthPx = 80;
summary.getRange("B:B").format.columnWidthPx = 90;
summary.getRange("C:C").format.columnWidthPx = 150;
summary.getRange("D:D").format.columnWidthPx = 520;
summary.getRange("E:E").format.columnWidthPx = 420;
summary.freezePanes.freezeRows(11);

const register = workbook.worksheets.add("Gap Register");
register.showGridLines = false;
addTable(
  register,
  "A1",
  ["ID", "Priority", "Module", "Confirmed Gap", "Code Evidence", "Business Impact", "Suggested Next Step"],
  gaps,
  "GapRegisterTable"
);
["A", "B", "C"].forEach((col, idx) => {
  register.getRange(`${col}:${col}`).format.columnWidthPx = [80, 90, 150][idx];
});
register.getRange("D:D").format.columnWidthPx = 430;
register.getRange("E:E").format.columnWidthPx = 360;
register.getRange("F:F").format.columnWidthPx = 430;
register.getRange("G:G").format.columnWidthPx = 430;
register.freezePanes.freezeRows(1);

const biz = workbook.worksheets.add("Business Functions");
biz.showGridLines = false;
addTable(
  biz,
  "A1",
  ["Business Function", "Current Coverage", "Gap / Not Yet Implemented", "Recommended Treatment"],
  businessGaps,
  "BusinessFunctionsTable"
);
biz.getRange("A:A").format.columnWidthPx = 220;
biz.getRange("B:B").format.columnWidthPx = 380;
biz.getRange("C:C").format.columnWidthPx = 520;
biz.getRange("D:D").format.columnWidthPx = 420;
biz.freezePanes.freezeRows(1);

const moduleSheet = workbook.worksheets.add("Module Counts");
moduleSheet.showGridLines = false;
moduleSheet.getRange("A1:B1").values = [["Module", "Gap Count"]];
styleHeader(moduleSheet.getRange("A1:B1"));
moduleSheet.getRange("A2:B" + (moduleCounts.length + 1)).values = moduleCounts;
moduleSheet.getRange("A:A").format.columnWidthPx = 240;
moduleSheet.getRange("B:B").format.columnWidthPx = 100;
const chart = moduleSheet.charts.add("bar", moduleSheet.getRange("A1:B" + (moduleCounts.length + 1)));
chart.title = "Confirmed Gaps by Module";
chart.hasLegend = false;
chart.setPosition("D1", "L18");
moduleSheet.freezePanes.freezeRows(1);

for (const sheet of [summary, register, biz, moduleSheet]) {
  const used = sheet.getUsedRange();
  used.format.wrapText = true;
  used.format.font = { name: "Aptos", size: 10 };
  used.format.verticalAlignment = "top";
}

const summaryPreview = await workbook.render({
  sheetName: "Summary",
  autoCrop: "all",
  scale: 1,
  format: "png",
});
await fs.writeFile(`${outputDir}/summary_preview.png`, new Uint8Array(await summaryPreview.arrayBuffer()));

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(outputPath);
