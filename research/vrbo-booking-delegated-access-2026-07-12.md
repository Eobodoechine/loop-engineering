# Domain Brief: Does Vrbo or Booking.com Offer a Native Delegated-Access Role Analogous to Airbnb's Co-Host?

**Date:** 2026-07-12
**Researcher mode:** D (domain research for a build)
**Build context:** Cockpit — PMS-competitor ingesting Airbnb, Vrbo, Booking.com, PadSplit.
**Prior finding this extends:** Airbnb's Co-Host role is native, permission-tiered, and
explicitly framed as agency (Co-Host Additional Terms: the delegate is "authorized ...
to act on its behalf and bind the Host"). This pass verifies whether Vrbo (Expedia Group)
and Booking.com have an equivalent *native dashboard* mechanism — explicitly excluding the
Expedia Rapid API / Booking.com Connectivity Partner integration paths, which are a
different (software-to-software) access model, not a human "add a teammate" role.

---

## Question 1 (Vrbo): Does Vrbo's own Owner Dashboard offer a native "co-host" / "team member" / "authorized user" role?

### Answer: No. Vrbo has no native multi-user/permission-tiered delegated-access role in the owner dashboard. The only mechanism Vrbo itself documents for a second person to act on an owner's account is full credential-sharing of the single "Expedia Group Account" login — which the Host Terms of Service actively *discourage* and for which the Host bears full liability, not agency-style shared authority.

**What I searched (documenting the negative, per the honesty bar):**
- WebSearch: `Vrbo owner dashboard add team member co-host property manager access`
- WebSearch: `site:help.vrbo.com property manager account access team`
- WebSearch: `Vrbo "add a co-host" OR "account access" help.vrbo.com`
- WebSearch: `help.vrbo.com "account access" invite user manage account`
- WebSearch: `Vrbo new feature 2026 add team member manage account users dashboard`
- WebSearch: `Expedia Group Vrbo "multiple users" OR "team access" owner account announcement`
- WebSearch: `Vrbo help "authorized contact" account communicate on your behalf` (inconclusive —
  see `not_found` below)
- Fetched and read (via `curl` + text extraction, not just search snippets):
  - `https://help.vrbo.com/articles/Manage-your-properties-in-the-Property-Manager-dashboard` (HTTP 200)
  - `https://help.vrbo.com/articles/Integrated-Property-Managers-About-the-Vrbo-dashboard` (HTTP 200)
  - `https://forever.travel-assets.com/flex/flexmanager/mediaasset/1336953-0_2-legal_partner_tos_vrbo_us_en.pdf` — **official Vrbo Host Terms of Service, "Effective From: 01 October 2025"** (HTTP 200, 29-page PDF, text-extracted and grepped in full)
  - Attempted `https://help.vrbo.com/category/Your_Account` — this is a JS-rendered SPA; static fetch returned only an Angular template stub (`<%- model.slug%>`), no usable content. Flagged, not treated as evidence of absence by itself — the absence conclusion rests on the ToS + the two articles above, plus convergent third-party confirmation below.

**Grounding quotes:**

1. **"Property Manager dashboard" is a red herring — it is bulk management of properties the owner ALREADY owns, not a delegated-access feature for adding another person.** From `help.vrbo.com/articles/Manage-your-properties-in-the-Property-Manager-dashboard`:
   > "The Property Manager dashboard allows you to manage all your properties in one place. ... Select one or more properties from the list and make the desired changes." (Bulk actions listed: Change tags, Archive/unarchive, Convert to Pay-per-booking.)

   No option to add a second user/collaborator appears anywhere in this article.

2. **The "Integrated Property Manager" (IPM) dashboard — Vrbo's only documented multi-actor structure — is explicitly the Rapid-API-adjacent software-connectivity path (out of scope per the question), and even it enumerates `Account Settings` with no user-management field:**
   From `help.vrbo.com/articles/Integrated-Property-Managers-About-the-Vrbo-dashboard`:
   > "As an Integrated Property Manager (IPM), you can use the Vrbo dashboard for a variety of reasons and features. IPMs are able to use the Vrbo dashboard to check invoices or pending transactions, read reviews, check listing status, and reply to inquiries and messages."
   > "Account Settings — You can update the following information via this page: Account-level contact information, Login email address, Password, Security questions, Two-factor authentication phone numbers, Pay-Per-Booking (PPB) payment preferences including credit card billing information."
   > "As an IPM, you should never use the Vrbo dashboard for the following tasks, as they are managed within the integrated software: Calendar, Reservations, Rates, Payments, Rental agreement, Cancellation policy, House Rules."

   This confirms IPM access is a **software-integration identity** (one account per connected PMS, provisioned by Vrbo/the software vendor), not a "invite a person as a teammate" feature — and its own `Account Settings` page has no add-user control.

3. **The operative clause — Vrbo's Host ToS treats any second person's access as raw password-sharing, with an explicit liability warning, NOT a defined permission role.** From the official Vrbo Host Terms of Service (§11.14, effective 01 October 2025):
   > "You agree to (i) keep your password and online ID for both your Expedia Group Account and your email account secure and strictly confidential, providing it only to authorized users of your Expedia Group Account, (ii) instruct each person to whom you give your online ID and password that he or she is not to disclose it to any unauthorized person... We discourage you from giving anyone access to your online ID and password for your Expedia Group Account with us and your email account. **However, if you do give someone your online ID and online password, or if you fail to safeguard such information, you are responsible for any and all transactions that the person performs while using your Expedia Group Account with us and/or your email account, even those transactions that are fraudulent or that you did not intend or want performed.**"

   This is the single clearest piece of evidence: the phrase "authorized users of your Expedia Group Account" appears, but it names a *security/liability concept* (whoever you handed the shared password to), not a *product feature* with its own login, permission tier, or defined data scope. There is no calendar/messages/reservations/payouts permission matrix anywhere in the document — because there is no second account to scope permissions on. Contrast directly with Airbnb's Co-Host Additional Terms, which define a named role, a selectable permission tier, and explicit agency language ("authorized ... to act on its behalf and bind the Host"). Vrbo's document instead frames shared access as a **risk the Host is warned against and bears full liability for**, which is close to the opposite of an endorsed agency relationship.

4. **The general "person acting on behalf of Host" clause in the ToS is about *legal signatory authority to bind the Host entity to the contract*, not a technical delegated-access role:**
   From §1.3: "If Host is a company, partnership or other entity, a person who uses our Service and/or agrees to these Terms on behalf of that Host represents that they have the authority to bind the entity to these Terms."
   This is boilerplate "who can sign for the company" contract law — every SaaS ToS has an equivalent clause — and is not evidence of a delegated-access *product* feature.

5. **Convergent third-party confirmation (not primary sources, but consistent across five independent vendors — used only as corroboration of the absence, not as a citation for any positive claim):** Hostfully, Hospitable, iGMS, PriceLabs, and 10xBnB blog posts (all discovered via WebSearch, not opened line-by-line as primary sources — flagged accordingly) uniformly state Vrbo "does not offer a native co-hosting feature like Airbnb," and describe the only workaround as either (a) full credential sharing, or (b) Vrbo support manually adding a second phone number for SMS two-factor authentication to the *same* account (still one login, one account — not a separate delegated identity). This matches exactly what the primary-source ToS and help articles show structurally (no add-user control exists anywhere in Account Settings).

**Conclusion for Vrbo:** No native "co-host"/"team member" role exists. The only in-dashboard mechanism for a second human to act on a Vrbo listing is sharing the single owner login (Expedia Group Account credentials), which Vrbo's own ToS discourages and treats as a Host liability, not a granted authority — a materially weaker and legally opposite framing from Airbnb's Co-Host. The only *documented* multi-actor identity on Vrbo (Integrated Property Manager) requires going through the software-connectivity path this question explicitly excludes.

---

## Question 2 (Booking.com): Does the Extranet offer a native "add user"/"team member" role, and is it framed as agency?

### Answer: Yes — the Booking.com Extranet has a real, native, permission-tiered multi-user system (Primary / Admin / User / Chain / Connectivity provider account types), created and managed entirely inside the Extranet UI, with granular per-area permissions. It is closer to Airbnb's Co-Host than Vrbo is, but its *permissions documentation* is framed as access control/security, not explicit agency language — the agency ("on behalf of the Accommodation") language exists instead in the General Delivery Terms' Messaging Service consent clause, applied to staff/agents/representatives generally, not tied specifically to the "User" account type by name.

**What I fetched (curl with a browser UA, since WebFetch returned 403 on these pages — confirmed real HTTP 200 responses, full page text extracted and read, not snippet-only):**
- `https://partner.booking.com/en-us/help/account-and-log/extranet-pulse/understanding-bookingcom-extranet-account-types-and-access` (HTTP 200) — **official Booking.com Partner Help**
- `https://partner.booking.com/en-us/help/account-and-log/settings/everything-you-need-know-about-primary-accounts` (HTTP 200) — **official Booking.com Partner Help**
- `https://admin.booking.com/hotelreg/terms-and-conditions.html?language=en` (HTTP 200) — **official General Delivery Terms (GDT), live/current version tag `v2601_nE_i`** — the actual contract, not a summary page

**Grounding quotes:**

1. **The account types, verbatim, from the official Extranet help article:**
   > "On the Extranet, you can create, manage, and remove user accounts. You can also manage their platform access. To manage different accounts, log in to the Extranet and select the User account icon. From the drop-down menu, select Create and manage users."
   > "Account types: Primary – an account created when you sign the initial contract with us. Admin – an account that holds all access rights to the Extranet and can manage other types of user accounts. User – a 'regular' account that can be created for your team members. Chain – an account created by our team upon request from chain property partners, which can't be self-managed. Connectivity provider – an account for connectivity providers that allows them to sign in to the Extranet with limited non-admin access."
   > "User account — This is a 'regular' user account that can be created for the team members who help manage your property. Permissions for these accounts can be changed by admin and primary accounts."

2. **Exact scope of what a "User" account can be granted — a real permission matrix, unlike Vrbo:**
   > "Permissions can be set for the following types of info and actions on the Extranet: Reservations – all areas related to reservation management, including change requests, charges, and guest messaging. Rates & availability – management of property inventory, availability, rates, and guest policies. Property details – edit information about the property, including the public content displayed to potential guests (e.g. descriptions, photos). Performance data – access to business performance data and analytics. Finance – access to financial documents and settings. Promotions – set up deals, discounts, and special offers. Notifications – access to messages from Booking.com, managing contact info, and other notification settings. Programs – management of opt-in programs like Genius and Preferred Partner. Manage users – add/remove users and change their Extranet permissions. Connectivity provider – manage connections with channel managers and other connectivity providers."

   This directly answers the "calendar, messages, reservations, payouts" part of the question: **yes to all** — Reservations (incl. guest messaging), Rates & availability (calendar), and Finance (payouts/financial documents) are each independently grantable/restrictable permission scopes for a User account, set by an Admin or Primary account holder via "Create and manage users" → "Add a user" → "Set up access rights."

3. **How a user is added (step-by-step, from the same official article):**
   > "To create a new user account on the Extranet: Sign in to the Extranet; Select the user account icon; Go to Create and manage users; On the next screen, go to Add a user; Enter the name and email of the new user; Click Next step: Set up access rights; Set the permissions for the new user account; Click Send invite."

4. **Is it framed as agency ("on behalf of")?** Not in the account-types/permissions help article itself — that document is framed entirely in access-control/security terms ("Permissions ensure that only the right people can access certain areas of your account... This helps keep your account secure"), with no "authorized to act on behalf of" language attached to the User role by name. However, the **General Delivery Terms (the actual contract)** does contain agency-flavored language, applied more broadly to staff/agents using the platform on the Accommodation's behalf — specifically in the Messaging Service clause (§2.9.2):
   > "The Accommodation understands and agrees that Booking.com will process (including storage, receipt, access, insight and screening) Communications and warrants that it has informed (and, as may be required by applicable laws, obtained all necessary authorisations from) its employees, agents, representatives, staff members and other individuals **prior to their use of the Messaging Service for or on behalf of the Accommodation.**"

   This is real agency language ("for or on behalf of the Accommodation") but it is a **data-privacy/consent warranty the Accommodation makes to Booking.com about its own staff**, not a grant-of-authority clause defining what the delegate is authorized to bind the Accommodation to (contrast Airbnb's Co-Host Additional Terms, which is precisely the latter). I did not find a Booking.com clause that says a "User" account is "authorized to act on [the Accommodation's] behalf and bind" it, the way Airbnb's Co-Host terms do explicitly.

5. **Also confirmed (Primary/Admin account-management article), for completeness on the org-account structure:**
   > "When you first register a property or portfolio with us, a primary account is created and linked to your Accommodation Agreement and Legal Entity ID (LEID). This account serves as the main account with full admin rights and is connected to all properties associated with the agreement."
   > "Control access rights of existing Extranet users or invite new ones" is listed as one of the things a primary account can do.

**Conclusion for Booking.com:** Yes, a native, self-service, permission-tiered delegated-access system exists in the Extranet (Primary/Admin/User account types; granular Reservations/Rates & availability/Finance/Property details/etc. permissions; added via "Create and manage users" → "Add a user" → set permissions → send invite), entirely independent of the Connectivity Partner API path. It is functionally the closest of the three non-Airbnb platforms to Airbnb's Co-Host model in terms of *mechanism* (a real invite-and-permission flow) but its *public documentation* frames it as access control/security rather than explicit agency; the closest agency-style language ("for or on behalf of the Accommodation") lives in the General Delivery Terms' Messaging Service consent clause and applies to the Accommodation's staff/agents generally, not as a defined attribute of the "User" account type specifically.

---

## Summary comparison table

| | Airbnb Co-Host (verified prior pass) | Booking.com Extranet "User" account | Vrbo Owner Dashboard |
|---|---|---|---|
| Native in-dashboard invite flow | Yes | Yes ("Create and manage users" → "Add a user") | **No** — no add-user control found anywhere in Account Settings, IPM dashboard, or Property Manager dashboard |
| Separate login/identity for delegate | Yes | Yes (own username/password) | **No** — delegate must use the owner's own Expedia Group Account credentials |
| Granular permission tiers (calendar/messages/reservations/payouts) | Yes, defined tier | Yes — Reservations (incl. messaging), Rates & availability, Finance, Property details, etc. independently toggleable | **N/A** — no permission system exists because there's no separate account |
| Explicit "authorized to act on behalf of / bind" agency language | Yes, in Co-Host Additional Terms | Partial — GDT §2.9.2 uses "on behalf of the Accommodation" for staff/agents generally re: Messaging Service consent, not as a named attribute of the "User" role | **No** — ToS §11.14 frames shared access as Host liability/risk it "discourages," not a granted authority |
| Path outside the API/Connectivity program | Yes | Yes | N/A (no such feature exists in or out of the API path) |

## not_found / could not verify
- A WebSearch summary claimed Vrbo lets an owner "designate someone as an authorized contact on your Vrbo account, which allows them to communicate with Vrbo on your behalf." I could not locate the underlying help.vrbo.com article for this claim after four targeted searches and one direct category-page fetch (the category page is a client-rendered SPA that returned no usable static content). This claim is **not verified** and should not be relied on — flagging it explicitly rather than either asserting or silently dropping it, per the honesty bar.
- I did not find a Booking.com Extranet help page that uses the specific word "co-host," "delegate," or explicit "act on behalf of and bind" language tied to the "User" account type by name (searched the account-types article and the primary-accounts article directly; did not exhaustively search every Extranet help article, e.g., the Finance-specific or Inbox-specific permission articles, which might contain additional framing).
- I did not check Booking.com's Partner-facing Privacy/Data Processing Agreement for additional agency language beyond GDT §2.9.2, since the question's scope was ToS/help-center delegated-access mechanics, not the full DPA.

## Constraints / gotchas for the Coder
- `partner.booking.com` blocks the plain WebFetch tool (HTTP 403) — likely bot detection on the default WebFetch user agent. `curl` with a standard browser User-Agent string succeeded (HTTP 200) for the same URLs. If the Coder or a future research pass needs to re-verify Booking.com partner docs, use a browser UA, not WebFetch directly.
- Vrbo's `help.vrbo.com` category pages (e.g., `/category/Your_Account`) are client-side-rendered (Angular-style `<%- model.slug %>` template artifacts appear in the raw HTML) — a plain `curl`/WebFetch will not see the article list; only individual `/articles/<slug>` pages return static, readable content.
- The Vrbo Host ToS PDF is hosted at a CDN path (`forever.travel-assets.com/flex/flexmanager/mediaasset/...`) that changes per version/region; the current US English version fetched here is dated "Effective From: 01 October 2025" — re-verify the effective date if this research is reused much later, since Vrbo revises this document periodically (the ToS itself states 30 days' notice of material changes).
- Local environment note (not platform-related): this machine's `pdftotext`/`pdftoppm` (poppler) install is broken (`Library not loaded: libtiff.5.dylib`), so the built-in Read tool cannot open PDFs directly here. Worked around by `pip install pypdf` and extracting text in Python. Future PDF research on this machine should expect the same failure and use the same workaround (or `pip install pypdf`) rather than assuming the PDF is unreadable.
