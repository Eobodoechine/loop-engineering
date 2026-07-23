# TaxAhead MVP Integration Tiering

Date: 2026-07-09
Repo catalog source: `src/lib/mock-data.ts`

## Evidence basis

This is a practical implementation matrix for the 199 providers in the demo catalog. It distinguishes:

- Direct user-authorized API: a normal OAuth/API flow TaxAhead can build against.
- Aggregator route: one connector unlocks many providers.
- File/email workaround: TaxAhead can still ingest tax artifacts via Gmail/Outlook/Drive/upload without a provider API.
- Partner-gated/API-key route: possible, but not a quick consumer MVP integration.
- Not MVP: legal/approval/security burden is too high for the pilot.

Sources checked:

- Gmail API: REST access to Gmail mailboxes, search/list/sync/push notifications and read-only extraction. https://developers.google.com/workspace/gmail/api/guides
- Microsoft Graph Mail: list/get messages, delta query, and change notifications. https://learn.microsoft.com/en-us/graph/api/resources/message
- Google Drive API: Drive file API and app platform. https://developers.google.com/workspace/drive/api/guides/about-sdk
- Dropbox HTTP API: app platform and file APIs. https://www.dropbox.com/developers/documentation/http/documentation
- Plaid: Link, Transactions, Investments, Liabilities, Statements, Income. https://plaid.com/docs/
- QuickBooks Online: REST/GraphQL accounting API, sandbox, partner-gated premium APIs. https://developer.intuit.com/app/developer/qbo/docs/get-started
- Stripe API: REST API with sandbox/test mode. https://docs.stripe.com/api
- PayPal REST APIs: OAuth 2.0, transaction search, webhooks; business account needed for live use. https://developer.paypal.com/api/rest/
- Square Developer: Payments, Orders, Catalog, Inventory, Team, Labor, SDKs and OAuth samples. https://developer.squareup.com/docs
- Shopify Admin API. https://shopify.dev/docs/api/admin-rest
- Amazon Selling Partner API: orders, payments, reports; public apps require Appstore approval. https://developer.amazonservices.com/
- eBay REST APIs: OAuth, selling/order/account/analytics APIs. https://developer.ebay.com/develop/guides-v2/using-ebay-restful-apis
- Etsy Open API v3. https://developers.etsy.com/documentation/
- Coinbase Developer Platform. https://docs.cdp.coinbase.com/
- Kraken REST/WebSocket/FIX APIs. https://docs.kraken.com/
- Gemini REST APIs and OAuth. https://developer.gemini.com/rest-api/rest-api
- Binance REST API. https://developers.binance.com/en/docs/products/spot/rest-api
- Gusto developer docs: Embedded Payroll and App Integration program. https://docs.gusto.com/
- Merge: unified API across HRIS, accounting, file storage and more. https://docs.merge.dev/home
- Railz/FIS Accounting Data as a Service: accounting, banking, commerce APIs and connect widget. https://docs.railz.ai/
- IRS transcripts: user can view/print/download records in IRS Online Account; no simple public consumer connector was found. https://www.irs.gov/individuals/get-transcript
- IRS MeF schemas/rules: filing infrastructure, not an MVP discovery connector. https://www.irs.gov/e-file-providers/modernized-e-file-mef-schemas-and-business-rules
- EFTPS: online tax payment system, not an obvious third-party data API for MVP. https://www.eftps.gov/eftps/

## Recommended MVP stack

### Tier 0: already built / should ship first

| Integration | Route | Why |
|---|---|---|
| Manual file upload | Current Supabase `create-upload` -> Storage -> `extract-document` -> facts/scores/package | Already implemented and aligned with uploads-first pilot. |
| Folder/ZIP upload | Extend current upload pipeline | Product-doc MVP includes folders/ZIP/mixed folders; implementation is mostly client batching + server extraction queue. |

### Tier 1: easiest real external connectors for MVP

| Integration | Route | Why |
|---|---|---|
| Gmail | Direct Gmail API OAuth | Best first external connector. Tax docs arrive as attachments/notifications; API supports search/list/sync/push. |
| Google Drive | Direct Drive API OAuth | Finds PDFs/folders/receipts; same Google OAuth platform as Gmail. |
| Outlook | Microsoft Graph Mail OAuth | Strong MVP equivalent to Gmail; supports messages, delta, notifications. |
| OneDrive | Microsoft Graph Files OAuth | Pair naturally with Outlook. |
| SharePoint | Microsoft Graph Files OAuth | Mostly business users; same platform as OneDrive but higher permission/admin complexity. |
| Dropbox | Direct Dropbox API OAuth | Straightforward file connector. |
| Box | Direct Box API OAuth, or Merge file-storage route | Feasible; more enterprise-oriented than Dropbox/Drive. |
| IMAP (Custom Email) | Generic IMAP + OAuth/app-password where available | Broad fallback for Fastmail, iCloud, Yahoo/AOL, Zoho, Proton Bridge-style cases, but auth UX varies. |

### Tier 2: high-leverage aggregator connectors

| Integration | Route | Providers covered | Why |
|---|---|---|---|
| Plaid | Plaid Link + Transactions/Investments/Liabilities/Statements/Income | Chase, Bank of America, Wells Fargo, Citi, Capital One, U.S. Bank, PNC, TD Bank, Truist, Ally, Discover Bank, American Express Bank, SoFi, Fidelity Cash Management, credit unions, many cards, some investments/loans | One integration covers banking, cards, transactions, liabilities, investments and statements. Best post-Gmail ROI. |
| MX | MX aggregator | Same broad bank/card category | Similar use case; sales/contracting likely heavier. |
| Finicity / Mastercard Open Banking | Finicity/Open Banking APIs | Same broad bank/card category | Similar to Plaid/MX; useful fallback if coverage/cost beats Plaid. |
| Merge | Unified API | HRIS/payroll/accounting/file storage categories | Useful for payroll/accounting breadth, but commercial onboarding required. |
| Railz/FIS Accounting Data as a Service | Unified accounting/banking/commerce API | QuickBooks/Xero/FreshBooks/Wave/Sage/Zoho Books plus commerce/banking coverage depending plan | Strong for small-business data if account/commercial access is acceptable. |

### Tier 3: direct APIs that are easy technically, but only valuable for specific user segments

| Providers | Route | MVP note |
|---|---|---|
| Stripe, Square, PayPal | Direct APIs/OAuth; PayPal live requires business account; Square has OAuth/SDK samples | Good for freelancers/sellers; tax value is 1099-K, gross receipts, fees. |
| Shopify, WooCommerce, BigCommerce, Squarespace Commerce | Direct commerce APIs/OAuth/app credentials | Good for small-business/seller profile; not needed for basic W-2 pilot. |
| Etsy, eBay | Direct marketplace APIs/OAuth | Useful for marketplace sellers; OAuth/API available. |
| Amazon Seller Central | SP-API | Powerful but approval/Appstore/role burden makes it harder than Shopify/Etsy/eBay. |
| Walmart Marketplace | Marketplace API | Possible but seller/marketplace approval burden; not first MVP. |
| QuickBooks Online, Xero, FreshBooks, Wave, Sage, Zoho Books | Direct APIs or Railz/Merge | Good for self-employed/business profile; QuickBooks/Xero are first choices. |
| Coinbase, Kraken, Gemini, Binance US, Crypto.com, OKX, Bybit | Exchange APIs/API keys/OAuth varies | Technically possible, but credential-security and tax-lot complexity are non-trivial. MVP workaround can ingest 1099s/CSV exports via email/upload. |
| CoinTracker, Koinly, CoinLedger, ZenLedger | Direct import/export/API where available, or user uploads tax reports | Easier than raw exchange integration for tax output if users already use these tools. |

### Tier 4: partner-gated, enterprise-heavy, or aggregator-first

| Providers | Best route | MVP note |
|---|---|---|
| Workday, ADP, Paychex, Gusto, Rippling, BambooHR, UKG, Ceridian Dayforce, Paycom, Paylocity, Square Payroll, Deel, Remote | Merge/Finch/Argyle/Pinwheel-style aggregator, or individual partner programs | Direct payroll integrations are not quick consumer OAuth builds. Best MVP workaround: W-2/paystub emails/uploads; next best: one payroll aggregator. |
| Fidelity, Charles Schwab, Vanguard, E*TRADE, Interactive Brokers, Merrill Edge, Webull, Public, SoFi Invest, Betterment, Wealthfront, M1 Finance, TD Ameritrade, Morgan Stanley, JP Morgan Self-Directed | Plaid Investments/Statements where covered; SnapTrade-style aggregator; email/upload tax forms | Direct retail brokerage APIs are inconsistent and often trading/account specific, not tax-doc focused. |
| Fidelity Retirement, Vanguard Retirement, Schwab Retirement, Empower, Principal, T. Rowe Price, Merrill, Human Interest, Guideline | Plaid/retirement statement aggregator where available; email/upload 1099-R/5498/plan docs | Direct consumer retirement APIs are generally not MVP-friendly. |
| Expensify, SAP Concur, Divvy/Ramp/Brex/Navan | Direct APIs or accounting/expense aggregators | Useful for business taxpayers; not core W-2 MVP. |
| Mercury, Brex, Ramp, BILL, Relay Financial, Navan | Direct APIs often business/partner oriented | Business-bank/expense segment; use Plaid/Railz/accounting first unless this is target persona. |
| Buildium, AppFolio, Rentec Direct, Avail, Stessa, TurboTenant | Direct APIs vary; rental statements/export/upload | Useful for landlords but long tail. For MVP, Airbnb + uploads/emails covers more. |
| Airbnb, Vrbo, Booking.com, Furnished Finder | Airbnb/Vrbo partner/API access limited; email/upload statements practical | Tax value is 1099-K/earnings/fees. Start with Gmail/Outlook discovery of host statements. |
| Uber, Lyft, DoorDash, Instacart, Shipt, Grubhub, Spark Driver, Amazon Flex, Roadie, TaskRabbit, Rover, Care.com, Upwork, Fiverr, Freelancer, Toptal, Contra, PeoplePerHour | Email/upload 1099s first; direct/partner APIs vary and are often unavailable for personal worker data | For gig/freelance MVP, detect platform emails and ingest 1099-NEC/1099-K PDFs. |

### Tier 5: do not build as direct MVP integrations

| Providers | Why |
|---|---|
| IRS Online Account, IRS Transcript Services, IRS Identity Protection PIN, State Tax Agencies, EFTPS | High legal/security burden; IRS supports user web account transcript download and MeF filing schemas, but not a simple consumer OAuth transcript API for TaxAhead MVP. Use upload/manual instructions first. |
| TurboTax, H&R Block, TaxAct, Cash App Taxes, FreeTaxUSA, Jackson Hewitt, TaxSlayer | Direct import APIs are not reliable open targets. Use prior-year PDF/CSV/TXF upload/import workflows. |
| Rocket Mortgage, Wells Fargo Home Mortgage, Chase Home Lending, Bank of America Mortgage, Mr. Cooper, LoanDepot, Better Mortgage | Mortgage data often comes via 1098 PDFs in email/mail/portal. Use email/upload/Plaid liabilities before direct servicer connectors. |
| Zillow, Redfin, Apartments.com | Public/search APIs do not solve user tax evidence; use them as enrichment later, not source-of-truth tax connectors. |
| Blue Cross Blue Shield, UnitedHealthcare, Aetna, Cigna, Kaiser Permanente | Healthcare APIs are regulated/complex and tax use is narrow. Use HSA providers/uploads for MVP. |
| HSA Bank, Optum Financial, HealthEquity, Fidelity HSA | Potentially useful but direct consumer APIs are not quick. Use email/upload of 1099-SA/5498-SA first. |
| Nelnet, Sallie Mae, Great Lakes, Common App, 529 Plans | Use email/upload for 1098-E/1098-T/529 statements first. Direct loan/education APIs are not MVP friendly. |
| Donorbox, Givebutter, Network for Good, Benevity, Charity Navigator | Donation receipts are best discovered in email or uploaded; direct connectors are low ROI. |
| Venmo, Cash App, Zelle, Wise, Revolut | Some APIs exist for business/payments, but personal transaction/tax access is inconsistent. Use 1099-K emails/uploads; PayPal/Stripe/Square first. |
| Ledger, Trezor, MetaMask, Phantom, Exodus, Coinbase Wallet | Wallet integrations require address discovery, chain indexing and tax-lot logic. MVP should accept exports or tax reports from crypto tax software. |

## All catalog providers, tiered

### Tier 1

Gmail, Outlook, Google Drive, OneDrive, SharePoint, Dropbox, Box, IMAP (Custom Email).

### Tier 1 fallback through IMAP/file discovery

Yahoo Mail, iCloud Mail, AOL Mail, Proton Mail, Fastmail, Zoho Mail, iCloud Drive, Mega, pCloud.

### Tier 2 via Plaid/MX/Finicity

Chase, Bank of America, Wells Fargo, Citi, Capital One, U.S. Bank, PNC, TD Bank, Truist, Ally, Discover Bank, American Express Bank, SoFi, Fidelity Cash Management, Credit Unions, Plaid (Aggregator), MX, Finicity, American Express, Chase Credit Cards, Capital One Cards, Citi Cards, Discover, Bank of America Cards, Wells Fargo Cards.

### Tier 3 direct/seller/business APIs

QuickBooks Online, Xero, FreshBooks, Wave, Sage, Zoho Books, Shopify, Etsy, eBay, Squarespace Commerce, WooCommerce, BigCommerce, PayPal, Stripe, Square, Coinbase, Kraken, Binance US, Gemini, Crypto.com, OKX, Bybit, CoinTracker, Koinly, CoinLedger, ZenLedger.

### Tier 3/4 depending on approvals or target persona

Amazon Seller Central, Walmart Marketplace, NetSuite, Oracle Financials, Workday, ADP, Paychex, Gusto, Rippling, BambooHR, UKG, Ceridian Dayforce, Paycom, Paylocity, Square Payroll, Deel, Remote, Mercury, Brex, Ramp, BILL, Relay Financial, Navan, Expensify, SAP Concur, Divvy, Airbnb, Vrbo, Booking.com, Furnished Finder.

### Tier 4 aggregator/email/upload first

Robinhood, Fidelity, Charles Schwab, Vanguard, E*TRADE, Interactive Brokers, Merrill Edge, Webull, Public, SoFi Invest, Betterment, Wealthfront, M1 Finance, TD Ameritrade, Morgan Stanley, JP Morgan Self-Directed, Fidelity Retirement, Vanguard Retirement, Schwab Retirement, Empower, Principal, T. Rowe Price, Merrill, Human Interest, Guideline.

### Tier 4 gig/freelance email/upload first

Uber, Lyft, DoorDash, Instacart, Shipt, Grubhub, Spark Driver, Amazon Flex, Roadie, TaskRabbit, Rover, Care.com, Upwork, Fiverr, Freelancer, Toptal, Contra, PeoplePerHour.

### Tier 5 not direct MVP

TurboTax, H&R Block, TaxAct, Cash App Taxes, FreeTaxUSA, Jackson Hewitt, TaxSlayer, IRS Online Account, IRS Transcript Services, IRS Identity Protection PIN, State Tax Agencies, EFTPS, Zillow, Redfin, Apartments.com, Rocket Mortgage, Wells Fargo Home Mortgage, Chase Home Lending, Bank of America Mortgage, Mr. Cooper, LoanDepot, Better Mortgage, Blue Cross Blue Shield, UnitedHealthcare, Aetna, Cigna, Kaiser Permanente, Nelnet, Sallie Mae, Great Lakes, Common App, 529 Plans, Donorbox, Givebutter, Network for Good, Benevity, Charity Navigator, HSA Bank, Optum Financial, HealthEquity, Fidelity HSA, Ledger, Trezor, MetaMask, Phantom, Exodus, Coinbase Wallet, Venmo, Cash App, Zelle, Wise, Revolut.

## Best MVP implementation order

1. Finish file/folder upload: multiple files, folder traversal, ZIP support, progress, queue, retry, `compute-scores` after extraction.
2. Gmail connector: OAuth, source row `type='gmail'`, search tax queries, attachment ingestion into existing document pipeline, Gmail history/watch later.
3. Google Drive connector: OAuth, scan selected folders/whole Drive metadata, ingest likely PDFs/images into existing pipeline.
4. Outlook + OneDrive connector: Microsoft Graph mail/files, same ingestion abstraction as Gmail/Drive.
5. Plaid connector: bank/card/transaction/statement coverage; create `source` rows for financial accounts and normalize statement/transaction evidence.
6. Stripe/Square/PayPal: small-business/freelance income.
7. QuickBooks Online/Xero, preferably through Railz/Merge unless direct OAuth is strategically better.
8. Marketplace/gig/crypto connectors only after the core evidence pipeline, source provenance, and member consent UI are solid.

## Product copy implication

For MVP, the UI should not imply that every catalog item is already a real connector. Use statuses:

- Ready: Uploads, Gmail after built.
- Next: Google Drive, Outlook/OneDrive, Plaid.
- Planned: Stripe, Square, PayPal, QuickBooks, Xero, Shopify, Coinbase.
- Import by email/upload: brokerages, payroll, gig platforms, mortgage, tax prep, IRS, healthcare, education, charity.

