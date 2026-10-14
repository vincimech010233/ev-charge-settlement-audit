# Evidence and novelty

Evidence labels follow the workspace convention: VERIFIED, OBSERVED, INFERRED, HYPOTHESIS, NOT_VERIFIED.

## Business problem

- **VERIFIED:** Volvo public charging support explains that an invoice total can differ from the total of listed sessions because other fees are added to the invoice and session detail depends on the charge-point operator. [Volvo support: invoice/session total mismatch](https://support.volvocar-public-charging.com/hc/en-gb/articles/28666518858769-Why-doesn-t-the-amount-on-my-invoice-match-the-total-of-my-charging-sessions)
- **VERIFIED:** BMW Charging publishes the same class of invoice-versus-session question and explains that other fees can be present outside individual session details. [BMW Charging support](https://support.bmw-public-charging.com/hc/en-gb/articles/28666428550801-Why-doesn-t-the-amount-on-my-invoice-match-the-total-of-my-charging-sessions)
- **VERIFIED:** Regulation (EU) 2023/1804 Article 5 requires transparent, comparable charging prices and makes session-specific price information a defined concern. This tool does not test legal compliance. [EUR-Lex, AFIR consolidated text](https://eur-lex.europa.eu/legal-content/en/ALL/?uri=CELEX%3A02023R1804-20260108)
- **INFERRED:** A finance team reconciling separate meter/session records and supplier invoice exports can use a local exception report to direct human investigation. The official pages establish user-facing invoice explainability issues, not the prevalence or financial value of this particular workflow.

## Competitors and differentiation

- **VERIFIED:** Monta documents operator transaction, invoice, and reimbursement features in its charging platform. [Monta invoice documentation](https://monta.com/help/en_US/monta-hub-payments-transactions-invoices/understand-monta-invoice)
- **VERIFIED:** EV24 documents a settlement workflow for charging services. [EV24 settlement documentation](https://docs.ev24.cloud/en/client/settlement/)
- **OBSERVED:** This repository implements a deliberately narrower complementary control: compare two already-exported, normalized CSV files offline, match by exact session ID, preserve duplicate and unmatched cases as exceptions, and emit hashes of the input files. It has no vendor account, charging control, payment initiation, or data upload.
- **NOT_VERIFIED:** Market demand, willingness to pay, measurable customer savings, and whether any named company would adopt this standalone utility.

## Owner-project novelty review

- **OBSERVED:** The inspected owner repository inventory includes OEE downtime analysis, production bottleneck simulation, bearing-life reliability, tolerance stack-up capability, satellite thermal modeling, Linux benchmarks/diagnostics, software supply-chain auditing, threat evidence correlation, and API contract checking. The local project records also contain these project areas and extensive model/physics work.
- **VERIFIED:** The owner's public [OEE and Downtime Analyzer](https://github.com/vincimech010233/oee-downtime-analyzer) source analyzes synthetic shift production metrics and downtime-cause Pareto charts; it does not reconcile EV invoices. Its [MIT license](https://github.com/vincimech010233/oee-downtime-analyzer/blob/main/LICENSE) and README/source were inspected. The public [Tolerance Stack-up Capability](https://github.com/vincimech010233/tolerance-stackup-capability) solves a dimensional engineering problem, not charging settlement; its README and MIT license were also inspected.
- **OBSERVED:** No repository in that inspected inventory is an EV charging invoice/session settlement reconciler. This is a finance-operations problem with exact-reference record matching and monetary/energy variance reporting, materially different from equipment efficiency, production simulation, mechanical reliability, and cybersecurity/CTI projects.
- **NOT_VERIFIED:** This review cannot establish that no similarly named tool exists anywhere on GitHub or in private repositories.
