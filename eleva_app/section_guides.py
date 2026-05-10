from collections import OrderedDict


SECTION_GUIDE_TEMPLATE = """Purpose

When to Use

Definitions

Workflow

Layout

Key Actions

System Impact

Rules / Restrictions

Common Mistakes

Best Practices

Related Sections"""


def _guide(title, content):
    return {
        "title": title,
        "content": content.strip(),
    }


SECTION_GUIDE_CONTENTS = OrderedDict(
    [
        (
            "dashboard",
            _guide(
                "Dashboard Process Guide",
                """
Purpose
The dashboard is the working cockpit for pending ERP work. It combines user-owned, team-owned, and recently created work from modules such as Sales, Customer Support, Projects, Design, QC, Service, SRT, Purchase, and Store.

When to Use
Use it at the start of the day to decide what needs action first, what is overdue, and which module needs follow-up.

Definitions
Pending means the downstream task is not closed or completed. Module grouping keeps work separated by ERP module. No grouping shows a single operating list.

Workflow
1. Select Table or Kanban view.
2. Select By Module or No Grouping.
3. Use due filters to narrow overdue, today, or next 7 days work.
4. Open the linked record and complete the action in its owning module.

Layout
The dashboard is a read surface, not the source of truth. Each card or row links back to the module that owns the record.

Key Actions
Switch view mode, switch grouping, filter by due date, open source records.

System Impact
Completing work on the dashboard requires updating the owning module record. Dashboard data follows those module states.

Rules / Restrictions
Do not treat the dashboard as an approval screen. Do not close work here unless the linked module route explicitly supports it.

Common Mistakes
Opening the same work in multiple tabs and updating stale data. Ignoring module grouping when ownership matters.

Best Practices
Use By Module for team review and No Grouping for personal prioritisation. Clear overdue work before creating new follow-up tasks.

Related Sections
Customer Support, Sales Tasks, Projects, Design Tasks, QC Tasks, Service Tasks, SRT, Purchase Orders.
""",
            ),
        ),
        (
            "customer_support",
            _guide(
                "Customer Support Process Guide",
                """
Purpose
Customer Support is the intake hub for calls, enquiries, complaints, support requests, and handoffs into Sales or Service.

When to Use
Use it when a customer contacts Eleva through toll-free calls, manual tickets, SARV-linked call history, email, or internal follow-up.

Definitions
Ticket is the support case. Linked task is downstream follow-up. SLA is the target response or resolution window. Linked entity can be sales client, installation project, AMC customer, lift, or sales opportunity.

Workflow
1. Review calls and existing tickets.
2. Create or open a ticket.
3. Assign owner, assignee, category, priority, and SLA.
4. Add linked entities and attachments.
5. Create linked tasks for Sales, Service, or internal follow-up.
6. Resolve only after downstream open tasks are completed.

Layout
Overview shows counts. Tasks & Tickets is the operating board. Call History and SARV test support telephony review.

Key Actions
Create ticket, update ticket, add comment, create linked task, resolve, close, delete when allowed.

System Impact
Sales NI or Sales AMC linked tasks can create qualified Sales Leads and Sales Opportunities. Lift-linked support tickets can create service visit entries.

Rules / Restrictions
Ticket closure is blocked while linked downstream tasks are open. SARV call records are not automatically complete tickets.

Common Mistakes
Closing the ticket before Sales or Service completes the linked work. Creating duplicate tickets for the same call without checking call history.

Best Practices
Link the customer, project, lift, and opportunity early. Use one ticket as the audit trail for the customer conversation.

Related Sections
Call History, SARV test, Sales Leads, Sales Opportunities, Service Tasks, Service Lifts.
""",
            ),
        ),
        (
            "customer_support_tasks",
            _guide(
                "Support Tickets Process Guide",
                """
Purpose
Support Tickets manage customer requests from intake to resolution with SLA, ownership, timeline, attachments, linked records, and downstream tasks.

When to Use
Use this section to create a ticket, triage a live customer issue, assign ownership, or hand work to Sales or Service.

Definitions
Owner is accountable for closure. Assignee is responsible for current action. Linked task is a downstream follow-up. Other Department tickets are filtered separately.

Workflow
1. Create or select a ticket.
2. Set category, channel, priority, owner, assignee, and SLA.
3. Attach related customer, lift, AMC site, sales client, or project.
4. Add comments and files as the case progresses.
5. Create linked tasks for Sales NI, Sales AMC, Service, or other follow-up.
6. Resolve or close after linked tasks are no longer open.

Layout
The list is SLA-sorted. The modal/detail area shows timeline, attachments, linked tasks, and update actions.

Key Actions
Create ticket, update fields, add comments, create linked task, resolve ticket, close ticket, delete ticket.

System Impact
Sales linked tasks can create qualified leads and opportunities. Service-linked lift tickets can generate service schedule entries. Timeline entries preserve operational history.

Rules / Restrictions
Do not resolve tickets with open linked tasks. Assign only users allowed for the selected support category.

Common Mistakes
Using free text instead of linking the actual lift or project. Treating a call record as a ticket without creating the ticket.

Best Practices
Use clear subject lines. Keep the timeline current. Link one ticket to all downstream work instead of creating parallel untracked work.

Related Sections
Customer Support Calls, Sales Leads, Sales Tasks, Service Tasks, Service Lifts.
""",
            ),
        ),
        (
            "customer_support_calls",
            _guide(
                "Call History and SARV Process Guide",
                """
Purpose
Call History records telephony evidence from SARV and manual/demo call sources for support review.

When to Use
Use this section to verify call date, number, call status, recording, duration, and whether a customer call needs a support ticket.

Definitions
SARV webhook/API data becomes CallLog and CallRecording records. A call record is evidence; a ticket is the operational case.

Workflow
1. Review recent calls or update SARV records.
2. Match the caller to customer, lift, project, or lead if possible.
3. Create or update the related support ticket.
4. Use the ticket to drive Sales or Service follow-up.

Layout
Call History lists calls. SARV test validates import/update behavior and webhook/API connectivity.

Key Actions
Update records, inspect call details, review recordings, use call context while creating tickets.

System Impact
Calls support ticket creation and audit trails. They do not by themselves qualify leads or close support work.

Rules / Restrictions
Localhost cannot receive external SARV webhook callbacks unless a tunnel or public URL is configured.

Common Mistakes
Expecting a call to automatically become a ticket. Missing the required webhook/API token setup.

Best Practices
Use the call record as evidence and create one clean ticket for follow-up. Keep phone numbers consistent across Sales and Service records.

Related Sections
Customer Support Tickets, SARV test, Sales Leads, Service Customers.
""",
            ),
        ),
        (
            "customer_support_settings",
            _guide(
                "Customer Support Settings Guide",
                """
Purpose
Customer Support Settings control assignment rules and support category behavior.

When to Use
Use this section when support categories, allowed assignees, or routing rules need operational tuning.

Definitions
Category controls the type of ticket. Assignment rule controls which users or positions can handle that category.

Workflow
1. Review current support categories and assignment constraints.
2. Update allowed positions or users.
3. Test by creating or updating a ticket in that category.

Layout
Settings are grouped around support routing and category assignment.

Key Actions
Adjust category assignment rules and save settings.

System Impact
Ticket creation and linked task assignment validation use these settings.

Rules / Restrictions
Do not remove all valid assignees from an active category unless the category should stop being used.

Common Mistakes
Changing assignment settings without testing ticket creation.

Best Practices
Keep categories aligned with actual support lanes: Sales NI, Sales AMC, Service, Breakdown, and internal follow-up.

Related Sections
Support Tickets, Admin Users, Sales Tasks, Service Tasks.
""",
            ),
        ),
        (
            "sales",
            _guide(
                "Sales Process Guide",
                """
Purpose
Sales manages lead qualification, clients, opportunities, tasks, CRFs, quotation documents, and conversion to new installation projects.

When to Use
Use it for new installation enquiries, AMC/service sales enquiries, campaign leads, and sales follow-up from toll-free calls.

Definitions
Lead is pre-pipeline intake. Qualified lead becomes an opportunity. Opportunity is the deal pipeline. Client is the customer/account record.

Workflow
1. Capture lead manually, by CSV, or from Customer Support linked task.
2. Qualify or reject the lead.
3. Work the opportunity pipeline.
4. Capture CRF, quotation request, quotation files, amount, items, and final documents.
5. Close won only when required final documents are present.
6. Convert won opportunities into Projects.

Layout
Sales dashboard summarizes activity. Leads, Tasks, Opportunities, Clients, and Settings are separate operating sections.

Key Actions
Create/import leads, qualify leads, create tasks, update opportunity stages, close opportunities, convert to projects.

System Impact
Qualified leads auto-create opportunities. Closed-won opportunities can create one or more Projects.

Rules / Restrictions
Do not bypass lead qualification when campaign conversion tracking matters. Closed-won conversion requires valid opportunity state and operations access.

Common Mistakes
Creating duplicate clients instead of matching phone/email/name. Closing won without final CRF and quotation evidence.

Best Practices
Use Sales Leads for campaign performance. Keep opportunity items accurate because project creation uses them.

Related Sections
Customer Support, Sales Leads, Opportunities, Projects, Project Templates.
""",
            ),
        ),
        (
            "sales_leads",
            _guide(
                "Sales Leads Process Guide",
                """
Purpose
Sales Leads tracks fresh, qualified, and rejected leads for New Installation and Service/AMC pipelines.

When to Use
Use it before opportunities when the enquiry still needs validation or when campaign conversion must be measured.

Definitions
Fresh means not yet qualified. Qualified means valid lead and creates/links an opportunity. Rejected means not sales-ready. Pipeline decides whether it becomes lift/new installation or service/AMC opportunity.

Workflow
1. Add a lead manually, by CSV upload, or via Customer Support linked Sales task.
2. Select New Installation or Service pipeline.
3. Set source such as Call on toll free, campaign, referral, or manual.
4. Qualify valid leads or reject invalid leads.
5. Work the created opportunity.

Layout
Lead lists can filter by pipeline and status. Upload template defines import columns.

Key Actions
Create lead, upload CSV/XLSX, update status, qualify, reject.

System Impact
Qualifying a lead creates or links a SalesClient and SalesOpportunity. Rejected leads remain measurable but do not enter the opportunity board.

Rules / Restrictions
Do not mark a lead qualified unless contact and business intent are verified.

Common Mistakes
Putting unqualified campaign data directly into Opportunities. Missing source values, which weakens campaign analysis.

Best Practices
Always set source and pipeline. Use rejection status instead of deleting weak leads.

Related Sections
Customer Support Tickets, Sales Opportunities, Sales Clients, Sales Tasks.
""",
            ),
        ),
        (
            "sales_tasks",
            _guide(
                "Sales Tasks Process Guide",
                """
Purpose
Sales Tasks manage follow-up work tied to clients, opportunities, or general sales activities.

When to Use
Use it for calls, quotation follow-ups, document collection, CRF completion, negotiations, and reminders.

Definitions
Owner is accountable. Assignees perform the task. Related reference links the task to an opportunity or client.

Workflow
1. Create a task from Sales or linked support flow.
2. Set due date, category, owner, and assignees.
3. Work from task board or calendar.
4. Open detail to see related CRF or quotation evidence.
5. Mark completed when the follow-up is done.

Layout
Taskboard groups tasks by category. Calendar groups by due date.

Key Actions
Create task, assign users, open detail, complete task.

System Impact
Completed tasks reduce dashboard pending work. Related opportunity/client context remains linked for audit.

Rules / Restrictions
Assignees must be users who can work in Sales.

Common Mistakes
Creating unlinked general tasks when the work belongs to a specific opportunity.

Best Practices
Link sales work to the relevant client or opportunity and keep due dates realistic.

Related Sections
Sales Leads, Opportunities, Clients, Dashboard.
""",
            ),
        ),
        (
            "sales_clients",
            _guide(
                "Sales Clients Process Guide",
                """
Purpose
Sales Clients stores prospect and customer account details used by leads, opportunities, and quotations.

When to Use
Use it when creating or cleaning customer/account records before or during sales work.

Definitions
Client is the sales-side customer record. Company groups related contacts. Lifecycle stage describes sales maturity.

Workflow
1. Search existing clients before creating new records.
2. Add client/contact/company data.
3. Link leads and opportunities.
4. Keep phone, email, company, and ownership accurate.

Layout
Client list supports search/upload/export. Detail page shows activity and linked sales records.

Key Actions
Create client, upload clients, export clients, inline update, open summary.

System Impact
Lead qualification may auto-create a client if no match is found. Opportunities and tasks use client links for context.

Rules / Restrictions
Avoid duplicate client records for the same phone/email/company.

Common Mistakes
Entering site names as client names without keeping contact details.

Best Practices
Use consistent naming and phone formats. Keep ownership current.

Related Sections
Sales Leads, Sales Opportunities, Customer Support Tickets.
""",
            ),
        ),
        (
            "sales_opportunities",
            _guide(
                "Sales Opportunities Process Guide",
                """
Purpose
Opportunities manage active sales deals through configured pipelines until won, lost, or converted to projects.

When to Use
Use after lead qualification or for direct valid enquiries that already belong in a sales pipeline.

Definitions
Pipeline is lift/new installation or service. Stage is the current selling step. CRF is client requirement form. Final quotation is the quote evidence used before closing won.

Workflow
1. Create opportunity manually or through qualified lead.
2. Add client, owner, amount, temperature, and items.
3. Capture CRF and quotation request/files.
4. Move through stages as evidence is completed.
5. Close won/lost with reason.
6. Convert won new-installation opportunities into Projects.

Layout
Kanban board groups opportunities by stage. Detail page stores comments, files, CRF, quotation, items, and close actions.

Key Actions
Create opportunity, move stage, add files/comments/items, request quotation, close, convert to project.

System Impact
Closed-won conversion creates Projects from opportunity items and links project IDs back to the opportunity.

Rules / Restrictions
Do not close won without required final CRF and quotation. Conversion needs Operations access.

Common Mistakes
Using opportunity title for technical scope while leaving item details empty.

Best Practices
Keep items accurate: lift type, floors, stops, location, finishes, and structure values flow into project creation.

Related Sections
Sales Leads, Sales Tasks, Projects, Design, Purchase.
""",
            ),
        ),
        (
            "sales_settings",
            _guide(
                "Sales Settings Guide",
                """
Purpose
Sales Settings controls templates and configuration used by sales processes.

When to Use
Use it when CRF structure, sales setup, or supporting sales controls need updates.

Definitions
CRF is the client requirement form used as sales and project evidence.

Workflow
1. Review current sales settings.
2. Update templates or controls.
3. Test on a non-critical opportunity before using in active work.

Layout
Settings are grouped for sales configuration.

Key Actions
Update sales settings and save.

System Impact
Changes affect future sales records and forms, not necessarily old submitted documents.

Rules / Restrictions
Do not change active templates without understanding downstream project and quotation impact.

Common Mistakes
Editing settings while active users are filling forms.

Best Practices
Version important requirement changes and communicate to sales/design teams.

Related Sections
Sales Opportunities, Forms, Projects.
""",
            ),
        ),
        (
            "projects",
            _guide(
                "Projects Process Guide",
                """
Purpose
Projects are the operational delivery container for new installation work after sales closure.

When to Use
Use Projects to manage site delivery tasks, cross-module task creation, comments, project specifications, and installation progress.

Definitions
Project is the delivery record. Project Task is a task within the project. Template creates standard tasks. Linked record connects a project task to QC, SRT, Design, or other module work.

Workflow
1. Create project manually or convert a closed-won sales opportunity.
2. Review project details from sales/opportunity items.
3. Apply a project template.
4. Work tasks in sequence and follow dependencies.
5. Use linked Design, QC, SRT, Purchase, and Store sections for module-specific work.

Layout
Project list shows all projects. Detail page shows specifications, tasks, comments, and linked records.

Key Actions
Create project, edit project, apply template, create task, add comments, open linked module records.

System Impact
Templates can create Project Tasks and linked SRT, Design, and QC records. Project details feed procurement plans and BOM context.

Rules / Restrictions
Do not treat Projects as sales leads. A project should represent committed delivery work.

Common Mistakes
Applying templates before project details are correct. Creating module work manually without linking to the project.

Best Practices
Keep project technical fields accurate because downstream BOM, procurement, and QC use them.

Related Sections
Sales Opportunities, Project Templates, Design Tasks, QC Tasks, SRT, Procurement Plan.
""",
            ),
        ),
        (
            "project_templates",
            _guide(
                "Project Templates and NI Settings Guide",
                """
Purpose
Project Templates define standard delivery task structures for new installation projects.

When to Use
Use this section when changing the standard installation process, task sequence, dependencies, or module handoffs.

Definitions
Template is a reusable project plan. Template Task can create linked work in modules such as QC, SRT, and Design. Dependency controls task order.

Workflow
1. Create or open a template.
2. Add task names, sequence, duration, module, and subtype.
3. Set dependencies.
4. Save or reorder tasks.
5. Apply the template to a real project only after review.

Layout
Template list shows available templates. Detail page manages tasks and ordering.

Key Actions
Create template, edit template, reorder tasks, delete task, save as task template.

System Impact
Template changes affect future project applications. Existing projects are not automatically rebuilt.

Rules / Restrictions
Do not delete or reorder active standard tasks without checking operations impact.

Common Mistakes
Using template task names too broadly, making dashboard ownership unclear.

Best Practices
Keep templates practical and stage-based: site readiness, design, procurement, installation, QC, handover.

Related Sections
Projects, SRT, Design Tasks, QC Tasks.
""",
            ),
        ),
        (
            "forms",
            _guide(
                "Forms and Submissions Guide",
                """
Purpose
Forms define structured checklists and data capture used by QC and other operational workflows.

When to Use
Use Forms to create, edit, preview, fill, or review structured submissions.

Definitions
Form Schema is the template. Submission is a completed response. Photo/video requirements can be tied to negative answers.

Workflow
1. Create or edit the form schema.
2. Preview the form.
3. Fill the form from a work item or direct form route.
4. Review submissions and attachments.

Layout
Forms list manages templates. Render page captures responses. Submission page displays saved data.

Key Actions
Create form, edit form, duplicate, delete, fill, preview, review submission.

System Impact
QC work completion percentages and evidence depend on form submissions.

Rules / Restrictions
Do not change active inspection forms casually once field teams rely on them.

Common Mistakes
Deleting a form that is still used in QC work.

Best Practices
Keep form questions specific and measurable. Use required photo rules for non-OK findings.

Related Sections
QC Tasks, QC Settings, Submissions.
""",
            ),
        ),
        (
            "design",
            _guide(
                "Design Process Guide",
                """
Purpose
Design manages engineering tasks, drawings, revisions, drawing history, BOM templates, BOM packages, and part classification.

When to Use
Use after a project needs engineering input or when drawings/BOMs must be prepared for procurement.

Definitions
Design Task is engineering work. Drawing Site stores project drawing history. BOM Package contains material requirements. Part Class maps design categories to purchase parts.

Workflow
1. Receive or create design task from project workflow.
2. Upload or update drawings/revisions.
3. Create BOM package or generate BOM from template.
4. Complete missing specifications.
5. Finalize BOM for procurement.
6. Handle spec changes before or after PO creation.

Layout
Overview summarizes design. Tasks show work queue. Drawing History and BOM Templates manage engineering records.

Key Actions
Create/update design task, upload drawing revision, create BOM, edit BOM lines, finalize package.

System Impact
Finalized/current BOM data drives Procurement Plan and PO line generation.

Rules / Restrictions
Do not procure from incomplete or obsolete BOM data. Spec changes after PO creation create sync risk.

Common Mistakes
Leaving BOM item specifications blank. Using manual descriptions where a Product/Part mapping exists.

Best Practices
Keep drawings and BOM packages linked to the correct project/site and revision.

Related Sections
Projects, Design Tasks, Drawing History, BOM Templates, Part Classes, Procurement Plan.
""",
            ),
        ),
        (
            "design_tasks",
            _guide(
                "Design Tasks Process Guide",
                """
Purpose
Design Tasks track engineering work, assignments, drawing inputs, task status, comments, and BOM output.

When to Use
Use when engineering needs to prepare drawings, clarify inputs, or produce BOM information for a project.

Definitions
Pending inputs means the task still lacks required information. Drawing revision is uploaded evidence. Task BOM is the material output linked to the task.

Workflow
1. Open or create the design task.
2. Assign owner/assignee and confirm inputs.
3. Upload drawings or revisions.
4. Build or update BOM packages and lines.
5. Resolve missing specifications.
6. Update task status.

Layout
Task board lists assignments. Detail page contains drawings, comments, BOM, and status actions.

Key Actions
Update status, add comments, upload drawings, manage BOM lines/packages.

System Impact
Design BOM records feed Procurement Plan and Purchase Orders.

Rules / Restrictions
Do not mark work complete if drawings/BOM are still incomplete for procurement.

Common Mistakes
Uploading drawing files without linking the correct project/site context.

Best Practices
Use comments for engineering clarifications and keep BOM package names clear.

Related Sections
Projects, Drawing History, BOM Templates, Procurement Plan.
""",
            ),
        ),
        (
            "drawing_history",
            _guide(
                "Drawing History Guide",
                """
Purpose
Drawing History stores engineering drawing records and revisions by site/project.

When to Use
Use it to review the latest drawing number, revision, drawing status, and historical design changes.

Definitions
Drawing Site is the site-level drawing record. Drawing Version/Revision stores drawing file and version history. Status Log records status changes.

Workflow
1. Search or open a drawing site.
2. Review latest drawing and revision history.
3. Upload/import drawing history when needed.
4. Open site detail for comments, versions, and status.

Layout
List page summarizes sites. Detail page shows drawing numbers, versions, comments, and status log.

Key Actions
Upload history, open site detail, download latest revisions.

System Impact
Drawing history helps identify which design/BOM version should be used.

Rules / Restrictions
Do not use old drawings for procurement or installation without confirming revision status.

Common Mistakes
Mixing project names and site names inconsistently.

Best Practices
Keep drawing number, revision, and project linkage clean.

Related Sections
Design Tasks, BOM Templates, Projects, Procurement Plan.
""",
            ),
        ),
        (
            "drawing_site",
            _guide(
                "Drawing Site Detail Guide",
                """
Purpose
Drawing Site Detail is the project/site-level engineering record for drawings, revisions, comments, and BOM context.

When to Use
Use it when checking a specific project's drawing progression or engineering history.

Definitions
Latest drawing is the current visible drawing reference. Revision is a file/version entry. Status log records engineering state changes.

Workflow
1. Confirm the site and project link.
2. Review latest drawing number and status.
3. Add or inspect comments and revisions.
4. Use linked BOM/procurement routes when material planning is needed.

Layout
The detail screen groups drawing metadata, revisions, comments, and related actions.

Key Actions
Update status, add comments, review/download revisions.

System Impact
Correct drawing status reduces procurement and installation mismatch.

Rules / Restrictions
Do not treat drawing upload alone as approval unless the status says so.

Common Mistakes
Using a superseded revision for BOM or installation planning.

Best Practices
Use clear revision notes and keep latest drawing status current.

Related Sections
Design Tasks, Drawing History, Procurement Plan, Projects.
""",
            ),
        ),
        (
            "bom_templates",
            _guide(
                "BOM Templates Guide",
                """
Purpose
BOM Templates define reusable engineering material structures and formulas for elevator BOM creation.

When to Use
Use when standardising BOM generation by lift type, civil/fabrication/main package, and configurable inputs.

Definitions
Template contains inputs, stages, sections, and lines. Formula evaluates quantities from inputs. BOM Package is generated output for a real project.

Workflow
1. Create or edit template metadata.
2. Define inputs and expected data types.
3. Add stages, sections, and lines.
4. Use formulas where quantities depend on lift/project data.
5. Generate project BOM and verify output before procurement.

Layout
Template list manages templates. Editor handles inputs, stages, sections, and lines.

Key Actions
Create template, edit line, configure formula, duplicate BOM, update item stage.

System Impact
Template changes influence future generated BOMs and procurement demand.

Rules / Restrictions
Do not rely on formulas without checking generated quantities.

Common Mistakes
Creating duplicate lines for the same part class instead of using sections/stages.

Best Practices
Keep template lines specific, measurable, and mapped to Part Classes or Products wherever possible.

Related Sections
Design Tasks, Part Classes, Procurement Plan, Purchase Parts.
""",
            ),
        ),
        (
            "part_classes",
            _guide(
                "Part Classes Guide",
                """
Purpose
Part Classes connect engineering BOM categories to purchaseable parts and allowed sections.

When to Use
Use when BOM templates need standard categories or when procurement needs a primary part mapping.

Definitions
Part Class is an engineering category. Primary Part is the preferred Product mapping. Associated sections control where the class is expected.

Workflow
1. Review existing part classes.
2. Create or update class name and active status.
3. Map primary part where available.
4. Use part classes in BOM templates and BOM lines.

Layout
List/API-driven UI manages classes and primary part search.

Key Actions
Create class, update class, map primary part, disable class.

System Impact
Part class mapping helps procurement resolve BOM lines into Products and vendor rates.

Rules / Restrictions
Do not disable classes currently used in active BOMs without replacement.

Common Mistakes
Using vague names that procurement cannot match to real parts.

Best Practices
Keep one operational meaning per class and maintain primary part mappings.

Related Sections
BOM Templates, Purchase Parts, Procurement Plan.
""",
            ),
        ),
        (
            "procurement_plan",
            _guide(
                "Procurement Plan Process Guide",
                """
Purpose
Procurement Plan converts finalized/current BOM requirements into vendor-wise purchase requirements.

When to Use
Use after Design/BOM is ready and before creating or reviewing Purchase Orders for a project or BOM.

Definitions
Required quantity comes from BOM. Ordered quantity comes from PO lines linked to BOM items. Vendor group is based on resolved primary vendor or product/vendor rate data.

Workflow
1. Select project or BOM procurement plan.
2. Review BOM package and item requirements.
3. Check missing vendors or unresolved parts.
4. Generate or create POs for vendor groups.
5. Track ordered vs required quantities.

Layout
Plan shows projects/BOMs, vendor readiness, item status, and linked POs.

Key Actions
Open project/BOM plan, review vendor groups, generate PO lines, open linked POs.

System Impact
Purchase Orders preserve BOM linkage, allowing the plan to compare demand against ordered quantity.

Rules / Restrictions
Do not create procurement from incomplete specifications or wrong project BOM.

Common Mistakes
Ignoring missing vendor or primary part mappings.

Best Practices
Resolve part/vendor gaps before PO creation. Use plan status to avoid duplicate ordering.

Related Sections
Design BOM, Part Classes, Purchase Parts, Vendors, Purchase Orders, GRN.
""",
            ),
        ),
        (
            "purchase_orders",
            _guide(
                "Purchase Orders Process Guide",
                """
Purpose
Purchase Orders commit material purchases to vendors for projects, BOMs, or manual requirements.

When to Use
Use after procurement planning or when approved manual purchase requirements exist.

Definitions
Draft PO can be edited. Issued PO is sent/active and can be received by Store. Material status reflects receiving progress. BOM-linked lines keep source BOM identifiers.

Workflow
1. Create PO manually or from BOM/procurement plan.
2. Select vendor, project, BOM, dates, terms, and line items.
3. Save as Draft and review.
4. Issue/send PO when ready.
5. Store creates GRN against Issued POs.
6. PO may auto-close when received quantities satisfy material status rules.

Layout
PO list shows statuses and filters. Detail page shows lines, financials, PDF/email, issues, spec-change request, and closure state.

Key Actions
Create PO, edit draft, issue/send, download PDF, create vendor issue, request spec change, close/cancel where valid.

System Impact
PO lines update purchase tracking, BookInventory totals, procurement plan ordered quantities, and Store receiving eligibility.

Rules / Restrictions
GRN can only be created for Issued POs. Avoid changing BOM-linked specs without spec-change tracking.

Common Mistakes
Creating a PO against the wrong project or BOM. Issuing incomplete vendor terms.

Best Practices
Review BOM-linked line quantities and vendor contact before issuing.

Related Sections
Procurement Plan, Vendors, Purchase Parts, GRN, Inventory.
""",
            ),
        ),
        (
            "parts",
            _guide(
                "Purchase Parts Guide",
                """
Purpose
Purchase Parts maintains product/part master data used in BOMs, vendor rates, inventory, and purchase orders.

When to Use
Use when creating new purchasable items, updating specs/UOM, or linking vendor rates.

Definitions
Product is the part master. SKU/item code links purchase and inventory. Vendor rate stores vendor-specific pricing and history.

Workflow
1. Search for existing part by code/name.
2. Create or update product details.
3. Maintain vendor rates and purchase UOM.
4. Use the part in BOM templates or PO lines.

Layout
Parts list supports search. Detail page manages product fields and vendor rates.

Key Actions
Create part, update part, update vendor rate, inspect rate history.

System Impact
Parts link Design BOM, Purchase Orders, Store Inventory, and vendor analysis.

Rules / Restrictions
Avoid changing item code/SKU after stock or PO history exists.

Common Mistakes
Creating duplicate parts with slightly different names.

Best Practices
Use stable item codes, clear descriptions, and consistent UOM.

Related Sections
Part Classes, BOM Templates, Purchase Orders, Inventory, Vendors.
""",
            ),
        ),
        (
            "vendors",
            _guide(
                "Vendors Process Guide",
                """
Purpose
Vendors stores supplier records, contacts, issues, complaints, attachments, product rates, and PO history.

When to Use
Use before PO creation, while evaluating supplier performance, or when logging vendor quality/delivery issues.

Definitions
Vendor Contact is a contact person. Vendor Issue tracks QC fail, rejected material, late delivery, or other issue. Vendor Rate is part-specific pricing.

Workflow
1. Create or import vendor.
2. Add contacts and attachments.
3. Maintain product rates.
4. Review PO history and issues.
5. Resolve vendor issues with replacement, return, deviation, or scrap action.

Layout
Vendor list shows suppliers. Detail page groups contacts, rates, issues, attachments, and purchase history.

Key Actions
Create vendor, upload vendors, edit vendor, manage contacts, add issue, update issue, transfer contact, download attachment.

System Impact
Vendors feed PO creation, procurement grouping, vendor-rate selection, and quality tracking.

Rules / Restrictions
Do not delete/merge vendor records without checking existing POs and issues.

Common Mistakes
Creating vendors without contact details. Not logging QC failures against the vendor.

Best Practices
Keep primary contacts current and use issues for supplier accountability.

Related Sections
Purchase Orders, Procurement Plan, Purchase Parts, GRN.
""",
            ),
        ),
        (
            "purchase_settings",
            _guide(
                "Purchase Settings Guide",
                """
Purpose
Purchase Settings controls procurement stages and purchase workflow support data.

When to Use
Use when stages or purchase process options need to match current procurement practice.

Definitions
Procurement Stage describes material/purchase lifecycle grouping used in BOM and purchase views.

Workflow
1. Review existing stages.
2. Add or update stage names and order.
3. Test affected BOM/PO screens.

Layout
Settings list current stages and edit/create actions.

Key Actions
Create stage, update stage, reorder/disable where available.

System Impact
Stage labels can appear in BOM lines, PO lines, reports, and procurement views.

Rules / Restrictions
Do not rename active stages casually because historical reports become harder to read.

Common Mistakes
Creating overlapping stages with the same operational meaning.

Best Practices
Use stage names that match actual elevator procurement phases.

Related Sections
BOM Templates, Procurement Plan, Purchase Orders.
""",
            ),
        ),
        (
            "purchase_reports",
            _guide(
                "Purchase Reports Guide",
                """
Purpose
Purchase Reports provide PO and procurement analysis for vendor, project, status, and material tracking.

When to Use
Use for management review, delayed PO tracking, vendor comparison, and purchase history analysis.

Definitions
PO total is computed from PO lines and financial fields. Material status reflects Store receiving progress.

Workflow
1. Apply report filters.
2. Review PO totals, status, project, vendor, and dates.
3. Open PO detail for action.
4. Export or reset filters as needed.

Layout
Reports are tabular and filter-driven.

Key Actions
Filter, reset, open PO detail, inspect totals/status.

System Impact
Reports read existing PO and receiving data; they do not create transactions.

Rules / Restrictions
Use PO detail for operational updates, not reports.

Common Mistakes
Reading Draft POs as committed spend.

Best Practices
Separate Draft, Issued, Closed, and Cancelled POs during review.

Related Sections
Purchase Orders, Vendors, GRN, Inventory.
""",
            ),
        ),
        (
            "purchase_odoo_history",
            _guide(
                "Historical POs Import Guide",
                """
Purpose
Historical POs stores imported Odoo purchase history for reference and analysis.

When to Use
Use when reviewing old purchase data or importing past PO records.

Definitions
Historical PO is imported reference data, not necessarily an active operational PO in the current workflow.

Workflow
1. Upload Odoo historical PO file.
2. Review import result and row errors.
3. Use history for reference, vendor comparison, or analysis.

Layout
Import history and filterable PO history are shown separately from active PO operation.

Key Actions
Upload Odoo file, filter history, reset filters.

System Impact
Imported history supports analysis. It should not be treated as current GRN-ready PO flow unless converted/imported into active POs.

Rules / Restrictions
Do not receive material against historical records unless they are active Issued POs.

Common Mistakes
Confusing historical Odoo imports with live purchase orders.

Best Practices
Use history for comparison and auditing, not for current store transactions.

Related Sections
Purchase Orders, Purchase Reports, Vendors.
""",
            ),
        ),
        (
            "grn",
            _guide(
                "GRN / Receive Material Guide",
                """
Purpose
GRN records material received from vendors against Issued Purchase Orders and posts accepted quantities into inventory.

When to Use
Use when material physically arrives at Store from a vendor.

Definitions
GRN is Goods Receipt Note. Open GRN is editable before posting. Closed GRN posts inventory. QC OK stock becomes usable. NG/rejected stock becomes quarantined.

Workflow
1. Select an Issued PO.
2. Enter received quantity, invoice details, QC status, and notes.
3. Create GRN as Open.
4. Review GRN detail.
5. Close GRN to post inventory.
6. PO material status is recomputed and may auto-close.

Layout
Receive page lists Issued POs and pending quantities. GRN detail controls status and line edits before posting.

Key Actions
Create receipt, update receipt, close GRN, inspect receipt detail.

System Impact
Closing GRN increases physical inventory or quarantine, updates BookInventory received totals, updates PO material status, and may create vendor issues for failed material.

Rules / Restrictions
GRNs can only be created for Issued POs. Posted/closed GRN lines cannot be edited. Reopening does not reverse inventory.

Common Mistakes
Entering quantities above remaining PO quantity. Closing before QC status is correct.

Best Practices
Use QC notes for damaged/rejected material and log vendor issues through the automatic issue flow.

Related Sections
Purchase Orders, Vendors, Inventory, Purchase Reports.
""",
            ),
        ),
        (
            "inventory",
            _guide(
                "Inventory Overview Guide",
                """
Purpose
Inventory Overview tracks stock quantities by item code after GRN postings, adjustments, reservations, and dispatches.

When to Use
Use to check usable stock, quarantined stock, low stock, book stock, and item movement history.

Definitions
Physical/current stock is actual usable quantity. Book stock accounts for reservations. Quarantined stock is received but not usable. Adjustment changes stock with audit reason.

Workflow
1. Review stock list and filters.
2. Open item movements for audit.
3. Use adjustment only for approved corrections.
4. Use delivery orders and DCs for operational outbound movement.

Layout
Overview shows summary and item table. Item movement pages show receipts, dispatches, and adjustments.

Key Actions
View stock, open item movements, adjust stock, inspect Odoo snapshot.

System Impact
Closed GRNs increase stock. Confirmed delivery orders reserve book stock. Completed DCs reduce physical stock. Adjustments create StockAdjustment records.

Rules / Restrictions
Do not use manual adjustments for normal dispatch or receiving. Use GRN/DC workflows instead.

Common Mistakes
Confusing book stock with physical stock. Dispatching material without a confirmed delivery order/challan.

Best Practices
Use item movement history before adjusting stock. Keep item codes aligned with Purchase Parts.

Related Sections
GRN, Delivery Orders, Delivery Challan, Purchase Parts, Assets.
""",
            ),
        ),
        (
            "delivery_orders",
            _guide(
                "Delivery Orders Guide",
                """
Purpose
Delivery Orders request and reserve stock for project/site dispatch before Delivery Challan is completed.

When to Use
Use when material must be issued from Store to a project, site, vehicle, or internal requirement.

Definitions
Delivery Order is the request/reservation document. Reserved quantity reduces book stock. Delivery Challan records actual dispatch.

Workflow
1. Create delivery order with destination/project and items.
2. Review requested quantities.
3. Confirm the order to reserve book stock.
4. Create Delivery Challan from confirmed order.
5. Complete challan to reduce physical stock.

Layout
DO list shows orders and status. Detail page shows item reservation and dispatch progress.

Key Actions
Create delivery order, confirm order, open detail, create challan.

System Impact
Confirmed orders reserve book stock. Delivery Challans complete physical movement.

Rules / Restrictions
Do not dispatch directly from a draft delivery order.

Common Mistakes
Requesting quantity beyond book availability and ignoring warning.

Best Practices
Confirm reservation before arranging transport or site dispatch.

Related Sections
Inventory, Delivery Challan, Projects, Store Settings.
""",
            ),
        ),
        (
            "dc",
            _guide(
                "Delivery Challan Guide",
                """
Purpose
Delivery Challan records physical outbound material movement from Store.

When to Use
Use after a Delivery Order is confirmed and material is physically dispatched.

Definitions
DC is Delivery Challan. Physical dispatch reduces current stock when completed. DO reservation affects book stock before dispatch.

Workflow
1. Create DC from a confirmed Delivery Order.
2. Verify item codes and quantities.
3. Edit if still allowed.
4. Complete dispatch once material leaves Store.
5. Review inventory movements.

Layout
Dispatch page lists challans. Challan create/detail pages manage item lines and completion.

Key Actions
Create challan from DO, edit challan, complete dispatch, inspect dispatched items.

System Impact
Completed DC reduces physical inventory quantities and updates delivery progress.

Rules / Restrictions
Do not complete DC before material physically leaves Store.

Common Mistakes
Using DC to reserve stock instead of confirming Delivery Order first.

Best Practices
Keep challan quantities aligned with actual packed material.

Related Sections
Delivery Orders, Inventory, Projects.
""",
            ),
        ),
        (
            "assets",
            _guide(
                "Assets Process Guide",
                """
Purpose
Assets tracks reusable operational equipment for accountability, movement, repair, and lifecycle history.

When to Use
Use for helmets, harnesses, tools, machines, testing equipment, and other reusable operational items.

Definitions
Serialized asset has one physical item per record. Quantity-based asset tracks grouped reusable quantity. Status is authoritative persisted state. Movement history is append-only and must not be overwritten.

Workflow
1. Create asset manually or bulk-create serialized assets.
2. Assign class, type, code, location, custodian, condition, warranty, and calibration data.
3. Issue asset to employee/site.
4. Return asset with condition and outcome status.
5. Start and close repair when needed.
6. Review movement and repair history.

Layout
Asset list filters by code, class, type, status, custodian, location, and tracking mode. Detail page shows master data, issue/return/repair actions, movement timeline, and repair history.

Key Actions
Create asset, edit asset, issue, return, send for repair, close repair, decommission/lost status through allowed actions.

System Impact
Issue/return/repair actions update current status, custodian, location, condition, and create movement records.

Rules / Restrictions
Do not treat reusable operational assets as normal inventory stock. Serialization is driven by accountability requirements, not asset value.

Common Mistakes
Creating quantity-based records for accountable tools that should be serialized.

Best Practices
Prefer operational traceability over accounting abstraction. Keep custodian and location current.

Related Sections
Asset Movements, Repairs, Store Settings, Inventory.
""",
            ),
        ),
        (
            "asset_movements",
            _guide(
                "Asset Movements Guide",
                """
Purpose
Asset Movements is the audit trail for every asset status, location, custodian, issue, return, transfer, repair, breakdown, lost, or decommission action.

When to Use
Use it to answer who had an asset, where it moved, when condition changed, and why status changed.

Definitions
Movement is append-only history. Previous values show state before the action. New values show state after the action.

Workflow
1. Search by asset, movement type, custodian, or location.
2. Review chronological movement history.
3. Open asset detail for current state and next action.

Layout
Movement list is a read-only audit trail.

Key Actions
Filter/search, open asset detail.

System Impact
Movements are created by asset actions; they should not be manually overwritten.

Rules / Restrictions
Movement history is append-only and must not be overwritten.

Common Mistakes
Editing asset master directly instead of using issue/return/repair actions.

Best Practices
Use remarks to explain exceptions such as damage, loss, or manual corrections.

Related Sections
Assets, Repairs, Store Settings.
""",
            ),
        ),
        (
            "asset_repairs",
            _guide(
                "Asset Repairs Guide",
                """
Purpose
Asset Repairs tracks lightweight repair lifecycle for operational assets.

When to Use
Use when an asset needs vendor/workshop repair, inspection, cost capture, or repair closure decision.

Definitions
Open repair means asset is in repair. Repair closure decides final asset status: Inventory, Breakdown, or Decommissioned.

Workflow
1. Start repair from asset detail.
2. Capture sent by, vendor/agency, problem, estimate, and remarks.
3. Asset status becomes In Repair.
4. Close repair with actual cost, condition, and final status.
5. Movement history records repair send and return.

Layout
Repair list shows open and closed repair records. Asset detail also shows repair history.

Key Actions
Start repair, close repair, review repair history.

System Impact
Repair actions update asset status and create movement records.

Rules / Restrictions
Do not close repair without choosing the asset's final operational status.

Common Mistakes
Returning a damaged asset to Inventory without condition notes.

Best Practices
Record problem descriptions and actual costs for accountability.

Related Sections
Assets, Asset Movements, Store Settings.
""",
            ),
        ),
        (
            "store_settings",
            _guide(
                "Store Settings Guide",
                """
Purpose
Store Settings maintains operational store configuration, including asset settings.

When to Use
Use when configuring asset classes, asset types, locations, and store-related setup values.

Definitions
Asset Class is broad category. Asset Type is specific item type. Location is a controlled place such as Warehouse - Goa.

Workflow
1. Open Store Settings.
2. Review Asset Settings.
3. Maintain classes, types, and locations.
4. Return to asset creation once dropdowns are correct.

Layout
Settings are grouped in collapsible sections.

Key Actions
Create/update class, create/update type, manage locations.

System Impact
Asset code generation depends on class and type prefixes. Asset creation uses location dropdown values.

Rules / Restrictions
Use fixed 3-character class prefixes and 2-character type prefixes for asset code generation.

Common Mistakes
Changing prefixes after assets are already created.

Best Practices
Set prefixes before bulk creating serialized assets.

Related Sections
Assets, Asset Movements, Repairs.
""",
            ),
        ),
        (
            "asset_settings",
            _guide(
                "Asset Settings Guide",
                """
Purpose
Asset Settings controls asset classes, asset types, and asset locations used by operational asset tracking.

When to Use
Use before creating new asset families or when a new operational location is needed.

Definitions
Class prefix is 3 characters. Type prefix is 2 characters. Asset code is class prefix plus type prefix plus 3-digit serial.

Workflow
1. Create or update asset class.
2. Create or update asset type and link it to class.
3. Confirm location list.
4. Create assets using those dropdowns.

Layout
Class, Type, and Location settings appear in collapsible sections under Store Settings.

Key Actions
Add/edit class, add/edit type, add/edit location.

System Impact
Changes affect future asset code generation and asset form dropdowns.

Rules / Restrictions
Asset code length is fixed at 8 characters. Prefixes must remain stable after use.

Common Mistakes
Creating duplicate types for the same tool.

Best Practices
Keep class/type names operationally readable and prefix rules strict.

Related Sections
Assets, Asset Movements, Repairs.
""",
            ),
        ),
        (
            "service",
            _guide(
                "Service Process Guide",
                """
Purpose
Service manages installed lifts, customers, AMC/contracts, service tasks, preventive maintenance, complaints, and service automation visibility.

When to Use
Use after installation handover or when existing customers require maintenance, complaint handling, AMC work, or lift data updates.

Definitions
Customer is service-side account. Lift is installed equipment. Service Task is actionable field work. Contract controls AMC/commercial service coverage.

Workflow
1. Maintain customer and lift master records.
2. Create/update contracts and service schedules.
3. Create service tasks or receive support-linked visits.
4. Assign technicians and log work.
5. Track parts usage and close tasks.

Layout
Overview summarizes service. Tasks, Customers, Lifts, Contracts, Preventive Planner, and Settings handle specific workflows.

Key Actions
Create task, update customer/lift, create contract, generate schedule, assign visit, close service task.

System Impact
Lift data drives preventive maintenance, contracts, support linking, and service schedule snapshots.

Rules / Restrictions
Do not delete customer/lift records without checking contracts, files, comments, and service tasks.

Common Mistakes
Creating service tasks without linking the lift where known.

Best Practices
Keep lift codes, route, AMC status, and preferred service schedule current.

Related Sections
Customer Support, Service Tasks, Customers, Lifts, Contracts, Preventive Maintenance.
""",
            ),
        ),
        (
            "service_tasks",
            _guide(
                "Service Tasks Process Guide",
                """
Purpose
Service Tasks track field work for complaints, AMC visits, repairs, and installation support.

When to Use
Use when a technician or service owner must act on a site/lift issue.

Definitions
Task code identifies the job. Call type describes work. Assigned techs are stored on the task. Worklog is the field activity timeline. Parts used are recorded on the task.

Workflow
1. Create task manually or from support/service flow.
2. Link customer and lift where possible.
3. Assign technicians, priority, and media requirement.
4. Update status and worklog as work happens.
5. Add parts used.
6. Close when work is complete.

Layout
Task list is sortable. Detail page manages status, priority, worklog, parts, and closure.

Key Actions
Create task, update status/priority, add worklog, add parts, close task.

System Impact
Closed tasks leave dashboard pending work. Parts usage is logged on the service task; inventory deduction is not automatic in this handler.

Rules / Restrictions
Do not close without adequate worklog and media if required.

Common Mistakes
Leaving task unlinked to customer/lift, making history hard to trace.

Best Practices
Use clear worklog notes and assign real technicians.

Related Sections
Customer Support, Service Customers, Service Lifts, Parts & Materials.
""",
            ),
        ),
        (
            "service_customers",
            _guide(
                "Service Customers Guide",
                """
Purpose
Service Customers maintains the customer master for installed lifts and service contracts.

When to Use
Use when creating/updating service customers, uploading customer data, or reviewing customer lift history.

Definitions
Customer code identifies the service account. Customer detail links lifts, comments, address, files, and contracts.

Workflow
1. Search existing customers.
2. Create or upload customer data.
3. Add/update address and contact details.
4. Link lifts and contracts.
5. Add comments where needed.

Layout
List page supports search/export/upload. Detail page shows customer context and linked lifts.

Key Actions
Create customer, update customer, upload/export, add comments, delete when safe.

System Impact
Customer records feed lifts, service tasks, contracts, and support linkage.

Rules / Restrictions
Do not duplicate customers with minor spelling differences.

Common Mistakes
Using project/site names instead of legal/customer names without contact clarity.

Best Practices
Keep customer code and company name stable.

Related Sections
Service Lifts, Service Contracts, Customer Support.
""",
            ),
        ),
        (
            "service_lifts",
            _guide(
                "Service Lifts Guide",
                """
Purpose
Service Lifts stores installed elevator data, AMC status, schedule, route, comments, and files.

When to Use
Use to maintain lift master information, generate maintenance schedules, assign visits, and review service history.

Definitions
Lift code identifies installed equipment. AMC status indicates contract/coverage state. Service schedule stores planned/actual visit entries.

Workflow
1. Create or upload lift data.
2. Link lift to customer.
3. Maintain location, route, technical fields, and AMC status.
4. Generate schedule when contract/frequency is known.
5. Assign visits and add notes/comments/files.

Layout
Lift list supports search/import. Detail page shows technical data, schedule, notes, comments, and files.

Key Actions
Create lift, edit/update, generate schedule, assign visit, add notes, upload files, add comments.

System Impact
Lift records feed Service overview, Preventive Planner, Customer Support AMC site options, and contract linkage.

Rules / Restrictions
Do not change lift code casually after service history exists.

Common Mistakes
Missing route/AMC data, causing planner and support options to be weak.

Best Practices
Keep lift master clean after project handover.

Related Sections
Service Customers, Service Contracts, Preventive Planner, Customer Support.
""",
            ),
        ),
        (
            "service_contracts",
            _guide(
                "Service Contracts Guide",
                """
Purpose
Service Contracts manages AMC and service agreements, contract lifts, pricing, previews, print/PDF, and contract lifecycle.

When to Use
Use when creating, editing, reviewing, or printing customer service contracts.

Definitions
Contract links customer and one or more lifts. Contract template controls document rendering. Contract pricing supports standard rate and discounts.

Workflow
1. Select customer and lifts.
2. Set contract type, duration, frequency, dates, and price.
3. Preview contract.
4. Print/PDF as needed.
5. Link contract to lift AMC details.

Layout
Contract list, form, preview, print, and PDF routes support full contract lifecycle.

Key Actions
Create contract, edit contract, preview, print, export PDF.

System Impact
Contract data updates lift AMC context and service planning.

Rules / Restrictions
Do not create contract without correct linked lifts and dates.

Common Mistakes
Changing price without preserving reason/history in settings where applicable.

Best Practices
Preview document before sharing with customer.

Related Sections
Service Customers, Service Lifts, Service Settings, Preventive Planner.
""",
            ),
        ),
        (
            "service_complaints",
            _guide(
                "Service Complaints Guide",
                """
Purpose
Service Complaints gives service-side visibility of complaint/support work.

When to Use
Use to review complaints that require service attention, especially lift-linked support issues.

Definitions
Complaint is a service-impacting customer issue. Support ticket may be the original intake record.

Workflow
1. Review open complaints.
2. Open linked ticket/task/lift where available.
3. Create or update service task as needed.
4. Close operational work when completed.

Layout
Complaint list summarizes service-relevant cases.

Key Actions
Review complaint, open linked work, follow up in Service Tasks or Customer Support.

System Impact
Complaint visibility depends on support and service task data.

Rules / Restrictions
Do not close support complaints only from this view if linked tasks remain open.

Common Mistakes
Handling complaint outside the linked ticket/task trail.

Best Practices
Keep one chain of evidence from call/ticket to service task closure.

Related Sections
Customer Support Tickets, Service Tasks, Service Lifts.
""",
            ),
        ),
        (
            "service_parts_materials",
            _guide(
                "Service Parts and Materials Guide",
                """
Purpose
Service Parts and Materials gives visibility into parts used for service work.

When to Use
Use when reviewing service parts usage or preparing operational follow-up for field material.

Definitions
Parts used are currently recorded on service tasks as task-level usage entries.

Workflow
1. Review service task parts usage.
2. Confirm if stock movement is required.
3. Use Store workflows for formal issue/dispatch where inventory must change.

Layout
This section summarizes service material context.

Key Actions
Review parts/materials, open service task.

System Impact
Service task parts logging does not automatically deduct inventory in the current handler.

Rules / Restrictions
Use Store Inventory/DC workflows for actual stock movement.

Common Mistakes
Assuming service parts entry reduced store stock.

Best Practices
Record service usage for job history and coordinate formal stock issue separately.

Related Sections
Service Tasks, Inventory, Delivery Orders, Delivery Challan.
""",
            ),
        ),
        (
            "service_preventive_maintenance",
            _guide(
                "Preventive Maintenance Planner Guide",
                """
Purpose
Preventive Planner shows upcoming lift maintenance based on lift schedules, contract frequency, and route planning.

When to Use
Use for weekly/monthly service planning and overdue preventive maintenance review.

Definitions
Visit is a scheduled maintenance entry. Preferred date/day controls scheduling preference. Route groups field work.

Workflow
1. Review due and overdue visits.
2. Check technician/route context.
3. Assign or update visits.
4. Update lift schedule after field completion.

Layout
Planner summarizes scheduled visits and warnings.

Key Actions
Review schedule, assign visits, open lift detail.

System Impact
Planner reads lift schedule data and service contract/lift context.

Rules / Restrictions
Do not rely on planner if lift AMC data or schedule is missing.

Common Mistakes
Generating schedules without checking preferred service date rules.

Best Practices
Keep lift schedules current and routes clean.

Related Sections
Service Lifts, Service Contracts, Service Tasks.
""",
            ),
        ),
        (
            "service_automations",
            _guide(
                "Service Automations Guide",
                """
Purpose
Service Automations documents supported service automation flows and roles.

When to Use
Use when reviewing which service tasks can be automated or what configuration is expected.

Definitions
Automation flow is a described service process. Role capability defines who acts in that flow.

Workflow
1. Review flows and role capabilities.
2. Compare against current service process.
3. Configure related settings where supported.

Layout
The page lists flows, roles, and configuration options.

Key Actions
Review automation documentation and related settings.

System Impact
This section is informational unless paired with configured service routes/settings.

Rules / Restrictions
Do not assume a documented automation is active without checking configuration.

Common Mistakes
Treating automation descriptions as completed scheduled jobs.

Best Practices
Validate each automation path with one real service scenario.

Related Sections
Service Settings, Service Tasks, Preventive Planner.
""",
            ),
        ),
        (
            "service_settings",
            _guide(
                "Service Settings Guide",
                """
Purpose
Service Settings controls service routes, dropdowns, contract templates, pricing, and service configuration.

When to Use
Use before changing options that field teams, contracts, or lift records depend on.

Definitions
Dropdown option is a controlled field value. Route maps service locations/branches. Contract template renders service contract documents. Price records store service contract pricing.

Workflow
1. Choose settings tab.
2. Update routes, dropdowns, templates, or pricing.
3. Use import/export where available.
4. Test the affected service form or contract.

Layout
Settings are grouped by dropdowns, contracts, pricing, and routes.

Key Actions
Add/update/toggle/reorder dropdowns, import settings, update contract template, add/update/toggle price.

System Impact
Settings affect future service records, lift forms, contract pricing, and contract output.

Rules / Restrictions
Do not remove options still used by live records without a migration plan.

Common Mistakes
Changing pricing without reviewing contract templates.

Best Practices
Keep dropdown labels operationally clear and avoid duplicates.

Related Sections
Service Contracts, Service Lifts, Service Customers.
""",
            ),
        ),
        (
            "srt",
            _guide(
                "SRT Process Guide",
                """
Purpose
SRT tracks site readiness and site response tasks before or during installation.

When to Use
Use when a site must be visited, assessed for civil readiness, or marked ready for installation.

Definitions
SRT Task status moves through Scheduled, Site Visited, Pending Civil Work, Ready for Installation, and Closed.

Workflow
1. Create task manually or through project template.
2. Assign site/team/date/priority.
3. Update status after visit.
4. Record civil pending items or readiness.
5. Close when site readiness work is complete.

Layout
Overview shows board and filters. Sites page groups tasks by site. Settings manages SRT form templates.

Key Actions
Create task, update task, filter status, open site.

System Impact
SRT tasks created from project templates remain part of project execution visibility.

Rules / Restrictions
Do not mark ready if civil work remains pending.

Common Mistakes
Closing SRT task without updating project/site readiness context.

Best Practices
Use clear site names and due dates.

Related Sections
Projects, SRT Sites, SRT Settings, QC.
""",
            ),
        ),
        (
            "srt_sites",
            _guide(
                "SRT Sites Guide",
                """
Purpose
SRT Sites groups site-readiness tasks, contacts, interactions, and updates by site.

When to Use
Use when reviewing all readiness work for a particular installation site.

Definitions
Site groups related SRT tasks. Updates/interactions record field coordination.

Workflow
1. Select a site.
2. Review open and closed SRT tasks.
3. Check contacts and updates.
4. Continue work from the task board if action is required.

Layout
Site list and selected site detail show task and contact context.

Key Actions
Select site, review tasks, inspect contacts/updates.

System Impact
Site names are inferred from known sites and SRT tasks.

Rules / Restrictions
Keep site names consistent to avoid fragmented site views.

Common Mistakes
Creating tasks under slightly different site names.

Best Practices
Use the same project/site name used in Projects.

Related Sections
SRT, Projects, QC.
""",
            ),
        ),
        (
            "srt_settings",
            _guide(
                "SRT Settings Guide",
                """
Purpose
SRT Settings manages SRT form templates and notification-related configuration.

When to Use
Use when site-readiness forms or SRT template structure must change.

Definitions
SRT Form Template is a structured field checklist for SRT work.

Workflow
1. Open form templates tab.
2. Create, update, or delete template.
3. Adjust schema JSON only with care.
4. Test by creating/updating SRT task usage.

Layout
Settings page lists templates and schema content.

Key Actions
Create template, update template, delete template.

System Impact
Template changes affect future SRT data capture.

Rules / Restrictions
Do not break schema JSON structure.

Common Mistakes
Deleting templates that field teams still use.

Best Practices
Keep templates short and site-readiness focused.

Related Sections
SRT, SRT Sites, Projects.
""",
            ),
        ),
        (
            "qc",
            _guide(
                "QC Process Guide",
                """
Purpose
QC manages inspection work, form submissions, comments, logs, and rectification status for installation/service quality.

When to Use
Use when assigning or performing inspection work against a project, site, or QC template.

Definitions
QC Work is the inspection task. Submission is the filled form. Status includes Pending Inspection, Inspection Done, Rectification Pending, and Closed.

Workflow
1. Create QC work manually or from project template.
2. Assign owner/assignee, template, project, stage, lift type, and due date.
3. Fill inspection form.
4. Review submissions and media evidence.
5. Move status through inspection, rectification, and closure.

Layout
Overview shows summary. Tasks page lists QC work. Detail page shows submissions, comments, logs, assignment, and status actions.

Key Actions
Create QC work, assign, fill form, add comment, update status.

System Impact
QC work may create linked Project Tasks and appears in dashboard pending work.

Rules / Restrictions
Do not close QC work while rectification remains unresolved.

Common Mistakes
Using wrong template for lift type/stage.

Best Practices
Capture photo/video evidence for non-OK findings.

Related Sections
Projects, Forms, Submissions, SRT.
""",
            ),
        ),
        (
            "qc_tasks",
            _guide(
                "QC Tasks Guide",
                """
Purpose
QC Tasks is the operating board for inspection assignments and status updates.

When to Use
Use when managing open inspections, assigning inspectors, or reviewing QC work progress.

Definitions
Open filter excludes Closed. Completion percent is derived from latest submission field completion.

Workflow
1. Filter open or closed work.
2. Create work with template and project context.
3. Assign inspector.
4. Fill form and review evidence.
5. Update status and comments.

Layout
Task list shows site, stage, lift type, assignee, due date, status, and completion.

Key Actions
Create QC work, open detail, assign, comment, update status.

System Impact
QC work can create or link project task records.

Rules / Restrictions
Assignee must be a QC-assignable user.

Common Mistakes
Creating QC work without project linkage where project exists.

Best Practices
Use project and template fields to keep QC traceable.

Related Sections
QC, Forms, Projects.
""",
            ),
        ),
        (
            "qc_settings",
            _guide(
                "QC Settings Guide",
                """
Purpose
QC Settings manages inspection templates and QC-related form configuration.

When to Use
Use when creating or modifying QC inspection forms.

Definitions
Form Schema is the inspection checklist template. Primary forms appear first.

Workflow
1. Review existing forms.
2. Create or edit a form.
3. Set stage/lift type where relevant.
4. Preview and test before assigning QC work.

Layout
Settings list forms and routes to form editor.

Key Actions
Create form, edit form, duplicate, delete, preview.

System Impact
Future QC work uses the updated templates.

Rules / Restrictions
Avoid changing form meaning after submissions exist.

Common Mistakes
Using generic questions that do not support closure decisions.

Best Practices
Keep inspection criteria clear, measurable, and evidence-friendly.

Related Sections
QC Tasks, Forms, Submissions.
""",
            ),
        ),
        (
            "settings",
            _guide(
                "Settings Guide",
                """
Purpose
Settings manages workspace-level administration, account preferences, display themes, module permissions, and system options.

When to Use
Use for admin controls, profile/account settings, module visibility, upload limits, dropdown options, and workspace configuration.

Definitions
Admin tools affect multiple users. Module settings affect how users see and work across ERP modules.

Workflow
1. Choose the correct settings tab.
2. Update only the relevant control.
3. Save and verify the affected page.

Layout
Settings uses tabs: Admin, Account, Display, and Module Settings.

Key Actions
Update admin settings, profile/display preferences, module settings, dropdown values.

System Impact
Settings can affect user access, upload limits, UI behavior, and controlled field values.

Rules / Restrictions
Do not reset workspace or change permissions without confirming impact.

Common Mistakes
Changing module access while users are actively working without communication.

Best Practices
Make one settings change at a time and verify.

Related Sections
Admin Users, Process Guides, Service Settings, Store Settings.
""",
            ),
        ),
        (
            "process_guides",
            _guide(
                "Process Guides Admin Guide",
                """
Purpose
Process Guides stores and edits the operational help content shown in the top-right guide drawer for ERP sections.

When to Use
Use when a process changes or users need clearer operating guidance for a module.

Definitions
Section Key maps a page endpoint to a guide. Active guide is shown to users. Content is plain text with preserved line breaks.

Workflow
1. Create or edit guide by section key.
2. Use the standard content headings.
3. Activate the guide.
4. Open the target section and test the question-mark guide button.

Layout
Admin form edits one guide. Library lists all guides and activation status.

Key Actions
Create guide, edit guide, activate/deactivate guide.

System Impact
Active guides appear to users on mapped section pages.

Rules / Restrictions
Content is escaped plain text; do not enter HTML expecting it to render.

Common Mistakes
Using a section key that is not mapped to any route endpoint.

Best Practices
Keep guides operational, concise, and specific to Eleva elevator workflows.

Related Sections
Settings, Admin Users, all operational modules.
""",
            ),
        ),
        (
            "admin_users",
            _guide(
                "Admin Users Guide",
                """
Purpose
Admin Users manages accounts, departments, positions, roles, activity, and service manager flags.

When to Use
Use when adding users, changing roles, updating department/position hierarchy, or deactivating accounts.

Definitions
Role controls broad behavior. Module permissions control access/assignment. Department and Position define organization structure.

Workflow
1. Create or update department and position records.
2. Create user with role and active status.
3. Assign department, position, permissions, and service manager status if required.
4. Deactivate users instead of deleting operational history.

Layout
Admin panel includes upload controls, process guide shortcut, create user form, existing users, departments, and positions.

Key Actions
Create/update user, reset password, activate/deactivate, manage departments/positions, upload org structure.

System Impact
Permissions affect module visibility, task assignment, and admin actions.

Rules / Restrictions
Do not remove access without checking ownership of active tasks.

Common Mistakes
Creating active users without assigning module permissions needed for their work.

Best Practices
Use departments/positions to support cleaner assignment and reporting.

Related Sections
Settings, Dashboard, Customer Support Settings, Service Settings.
""",
            ),
        ),
    ]
)
