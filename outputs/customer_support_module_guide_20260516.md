# Customer Support Module Guide

Verified against the local Eleva ERP codebase on 2026-05-16.

## 1. Purpose

The Customer Support module is the intake and triage point for customer calls, enquiries, complaints, AMC support requests, NI support requests, and internal handoffs.

It is not only a ticket list. It connects customer contact events to:

- Support ticket tracking
- SARV call evidence
- Sales leads and sales enquiries
- New installation project references
- AMC customers and lift records
- Service visit scheduling for linked lift complaints
- Internal ownership and assignment controls

The module is designed around a support ticket. A call record is evidence. A ticket is the operational case that users act on.

## 2. Main Screens

### Customer Support Overview

Route: `/customer-support`

Shows summary KPIs for Customer Support tickets:

- Open
- In Progress
- Resolved
- Closed
- Recent tickets

Other Department tickets are excluded from the main summary counts by the current helper logic.

### Tasks & Tickets

Route: `/customer-support/tasks`

This is the main operating screen. Users can:

- Create a ticket
- View the ticket queue sorted by SLA due time
- Open ticket details
- Update status, priority, owner, and assignee
- Add comments and attachments
- Create linked tasks
- Create qualified Sales leads/enquiries from relevant support tickets
- Resolve tickets after closing remarks

### Call History

Route: `/customer-support/calls`

Shows call/interactions combined from three sources:

- Manual/demo support call records stored in Customer Support JSON state
- SARV `CallLog` database records
- Derived call entries from Customer Support tickets

Filters available:

- Status
- Category
- Search by subject, caller, or ticket ID

### SARV Test

Route: `/customer-support/sarv-test`

Shows the latest 50 SARV webhook calls stored in the `CallLog` table. It also has an `Update records` action.

Important: `Update records` does not pull new calls from SARV. It checks existing `CallRecording` rows and retries missing or failed recording downloads.

### Customer Support Settings

Route: `/customer-support/settings`

Admin-only. Used to configure which user positions are allowed to be assigned to each Customer Support category.

The settings are saved in `instance/customer_support_settings.json`.

## 3. Data Storage

### Support Tickets

Customer Support tickets are stored in:

`instance/customer_support_data.json`

The app loads this file into the in-memory `CUSTOMER_SUPPORT_TICKETS` list at startup and saves changes back to JSON.

Each ticket record stores fields such as:

- `id`
- `subject`
- `customer`
- `contact_name`
- `contact_phone`
- `contact_email`
- `category`
- `category_key`
- `channel`
- `priority`
- `status`
- `owner`
- `owner_user_id`
- `assignee`
- `assignee_user_id`
- `created_at`
- `updated_at`
- `sla`
- `attachments`
- `timeline`
- `linked_tasks`
- `linked_entities`

### Attachments

Ticket attachments are saved under the configured Flask upload folder and referenced through `/static/uploads/...`.

The timeline records whether an update was an internal note, external update, or attachment upload.

### SARV Calls

SARV call data is stored in database tables:

- `call_logs`
- `call_recordings`

Models:

- `CallLog`
- `CallRecording`

`CallLog` stores call metadata like SARV call ID, customer number, agent details, call status, IVR timing, answer/hangup timing, durations, and raw payload.

`CallRecording` stores recording file references and local download status.

## 4. Ticket Categories

The implemented Customer Support categories are:

| Category key | Label | Default first response | Default resolution |
|---|---:|---:|---:|
| `sales-ni` | Sales - NI | 4 hours | 24 hours |
| `support-ni` | Support - NI | 4 hours | 24 hours |
| `sales-amc` | Sales - AMC | 6 hours | 48 hours |
| `support-amc` | Support - AMC | 2 hours | 18 hours |
| `other-dept` | Other Department | 8 hours | 72 hours |
| `other-query` | Other Query | 12 hours | 120 hours |

Ticket channels are:

- Phone
- Email
- Web
- Walk-in
- WhatsApp

SLA presets are:

- Standard: first response 6 hours, resolution 48 hours
- Priority: first response 2 hours, resolution 18 hours
- Critical: first response 1 hour, resolution 8 hours

For `sales-ni`, `support-ni`, `sales-amc`, and `support-amc`, the ticket creation flow defaults to Critical SLA if the user does not choose another preset.

## 5. Ticket Creation Flow

Route: `POST /customer-support/tasks`

The create-ticket form is processed only when `form_name=create_ticket`.

Mandatory validation:

- Subject is required.
- Category is required.
- Intake channel is required.
- Customer is required except for `other-dept` and `other-query`.
- `support-amc` requires an AMC site selection.
- Owner and assignee, if selected, must be active ERP users assignable to Customer Support.
- Assignee must pass the Customer Support category-position rule if one is configured.
- If creating a Sales lead, the selected sales owner must be active and able to view Sales.

On success:

1. System generates the next ticket ID in `CS-####` format.
2. Ticket status starts as `Open`.
3. Priority starts as `Medium`.
4. Owner defaults to selected owner, otherwise current logged-in user.
5. Assignee defaults to selected assignee, otherwise `Unassigned`.
6. SLA is stored on the ticket.
7. Attachments are saved.
8. A first timeline event is added: `Ticket logged`.
9. Linked entity references are added where applicable.
10. The ticket is appended to `CUSTOMER_SUPPORT_TICKETS`.
11. JSON state is saved.

## 6. Linkage During Ticket Creation

The ticket creation form can link the ticket to:

- Sales client
- Installation project
- AMC customer
- Lift
- AMC site

When linked, the system also adds comments/activity to the linked record where implemented:

- Sales client gets a sales activity referencing the support ticket.
- Installation project gets a project comment.
- AMC customer gets a customer comment.
- Lift gets a lift comment.

## 7. Sales Lead and Enquiry Conversion

The module can create Sales leads/enquiries from Customer Support in two places:

1. During ticket creation, when `create_sales_lead` is selected.
2. From a linked task, when the linked task category is `sales-ni` or `sales-amc`.

Pipeline mapping:

| Customer Support category | Sales lead pipeline |
|---|---|
| `sales-ni` | `new_installation` |
| `sales-amc` | `service` |

Created lead behavior:

- Lead status is set to `qualified`.
- Lead source is set to `Call on toll free`.
- The lead is converted into a Sales opportunity through `convert_if_qualified=True`.
- For ticket-creation flow, the system also creates a sales call engagement and a Sales Task due today.
- The support ticket stores links back to the lead/opportunity.

Operational meaning:

- A new installation enquiry from support should enter the Sales new installation pipeline.
- An AMC/service sales enquiry from support should enter the Sales service pipeline.

## 8. Service Handoff Behavior

When a ticket is linked to a lift and the category appears service-related, the system attempts to create a service visit entry on that lift.

The service visit creation logic looks at:

- `linked_lift_id`
- `linked_lift.id`
- Category key
- Category label

It treats service-related labels containing words like AMC, service, breakdown, or complaint as service visit candidates.

If applicable, it appends a scheduled entry to the lift service schedule with:

- Date: today
- Status: scheduled
- Source: support_ticket
- Support ticket reference
- Complaint summary
- Checklist/category label

It avoids creating a duplicate visit for the same lift, same day, and same support ticket reference.

## 9. Ticket Queue and SLA

The ticket list calculates SLA due date as:

1. Explicit `due_at`, if present
2. Otherwise `created_at + ticket.sla.resolution_hours`

Tickets are sorted by SLA due time.

Other Department tickets are filtered out of the main Tasks & Tickets queue by current code.

## 10. Ticket Update Flow

Route: `POST /customer-support/tickets/<ticket_id>/update`

Users can update:

- Status
- Priority
- Owner
- Assignee

Allowed statuses:

- Open
- In Progress
- Resolved
- Closed

Allowed priorities:

- Low
- Medium
- High
- Critical

Rules:

- Owner and assignee must be valid active users.
- Assignee must pass category assignment settings if configured.
- Moving to Resolved or Closed requires closing remarks.
- Moving to Resolved or Closed is blocked while the ticket has open linked Customer Support tasks.
- Each real change adds a timeline entry.

## 11. Quick Resolve Flow

Route: `POST /customer-support/tickets/<ticket_id>/resolve`

Rules:

- Closing remarks are required.
- The ticket cannot be resolved if linked Customer Support tasks are still open.
- If current status is not already Resolved or Closed, status becomes Resolved.
- A status timeline entry and closing remarks entry are added.

## 12. Comments and Attachments

Route: `POST /customer-support/tickets/<ticket_id>/comment`

Rules:

- User must add a comment or at least one valid attachment.
- Attachments are saved to the upload folder.
- Timeline entry is marked internal or external depending on form input.
- Ticket `updated_at` is refreshed.

## 13. Linked Tasks

Route: `POST /customer-support/linked-tasks`

Linked tasks are stored inside the ticket JSON record under `linked_tasks`.

The linked task captures:

- ID
- Title
- Owner
- Assignee
- Status
- Due date
- Details
- Category
- Priority
- Optional URL
- Optional linked Sales lead/enquiry

Current closure rule:

- A linked task blocks ticket closure only when it is treated as a Customer Support/support-ticket task and remains open.
- Downstream handoff tasks with other related types are treated differently and do not always block closure.

## 14. SARV Webhook Flow

Webhook route: `/sarv/webhook`

This route is CSRF-exempt.

GET behavior:

- Returns `GODBLESSYOU`
- Used as a basic webhook verification/ping response

POST behavior:

1. Reads JSON payload.
2. If `callId` is missing, returns `GODBLESSYOU` with HTTP 200.
3. Finds or creates a `CallLog` by SARV `callId`.
4. Saves caller, agent, call status, IVR fields, time fields, duration fields, and raw payload.
5. Parses `recordings` if it is a list, dict, or JSON string.
6. Ignores unexpanded SARV placeholders like `{{%%recordings%%}}`.
7. Creates `CallRecording` rows for new recording files.
8. Attempts to download each new recording.
9. Returns `GODBLESSYOU` with HTTP 200.

Important operational note:

- SARV webhook records create call evidence, not support tickets.
- A call appearing in Call History does not mean a ticket has been created.
- A public URL or tunnel is required for SARV to reach a local development server.

## 15. SARV Recording Download

Recording download uses:

- `SARV_RECORDING_BASE_URL`, default `https://ctv1.sarv.com`
- `SARV_RECORDING_TOKEN`, optional bearer token
- `CALL_RECORDINGS_DIR`, default `static/call_recordings`

On success:

- File is saved locally.
- `CallRecording.local_file_path` is set.
- `download_status` becomes `success`.

On failure:

- `download_status` becomes `failed`.
- `download_error` stores the error text.

The SARV Test page `Update records` button retries missing or failed recording downloads for existing `CallRecording` rows. It does not fetch new SARV calls.

## 16. Permission and Visibility

Customer Support routes require login.

Module visibility keys used:

- `customer_support`
- `customer_support_tasks`
- `customer_support_calls`
- `customer_support_settings`

Settings page additionally requires admin access.

There is a special case in the Tasks & Tickets route: if a selected ticket has an owner or assignee, that user may be allowed to view the ticket modal even if general module visibility has changed.

## 17. Process SOP

Recommended working process:

1. Review Call History or incoming contact.
2. If action is required, create a support ticket.
3. Select the correct category:
   - Sales - NI for new installation sales enquiries.
   - Sales - AMC for AMC/service sales opportunities.
   - Support - AMC for breakdown, callbacks, and AMC site support.
   - Support - NI for new installation post-sale support.
   - Other Query only when it does not fit any operational bucket.
4. Link the customer, lift, AMC site, sales client, or project wherever possible.
5. Assign owner and assignee based on Customer Support settings.
6. For qualified sales enquiries, create the Sales lead/enquiry from the ticket.
7. For lift complaints, link the lift so Service can receive schedule context.
8. Add updates as internal or external comments.
9. Keep linked tasks updated.
10. Resolve only after downstream work is completed and closing remarks are added.

## 18. What The Module Does Not Currently Do

Based on current code:

- SARV calls do not automatically create Customer Support tickets.
- The SARV `Update records` button does not import all call history from SARV API; it retries recording downloads for already stored recordings.
- Tickets are not stored in a normalized database table; they are stored in JSON state.
- Other Department tickets are filtered out of the main ticket queue and summary by helper logic.
- There is no full email/WhatsApp integration shown in this module path; those channels are captured as ticket metadata.
- Ticket closure depends on linked task status, but downstream Sales/Service completion is not fully enforced unless represented in linked task logic.

## 19. Practical Control Points

For reliable operation, the business should ensure:

- Every customer-facing call that needs action becomes a ticket.
- SARV webhook is configured to a reachable public URL in production.
- Localhost testing uses a tunnel if SARV must send webhook callbacks.
- Customer Support Settings are maintained so category assignment follows actual departments.
- Sales enquiry creation is used only for verified qualified leads.
- Lift/AMC site linkage is used for service complaints, otherwise the Service handoff will be weak.
- The JSON state file is included in backup strategy because tickets live there.

## 20. Key Files Reviewed

- `app.py`
  - Customer Support constants and settings
  - Ticket creation/update/comment/resolve routes
  - Call history aggregation
  - Sales and Service handoff logic
- `integrations/sarv/routes.py`
  - SARV webhook ingestion
- `integrations/sarv/utils.py`
  - SARV recording download
- `eleva_app/models.py`
  - `CallLog`
  - `CallRecording`
- `templates/customer_support_overview.html`
- `templates/customer_support_tasks.html`
- `templates/customer_support_calls.html`
- `templates/customer_support_sarv_test.html`
- `templates/customer_support_settings.html`

