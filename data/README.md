# ECE-036 – Smart TV and Appliance Extended-Warranty Pricing and Claim Engine — Sample Data Pack

Prepared by 10 SECONDS for Team E014.

## Files

| File | What it holds | Row count |
|---|---|---|
| `customers.csv` | Policy holders | 60 |
| `policies.csv` | Extended-warranty policy purchases | 150 |
| `claims.csv` | Repair claims against policies | 90 |
| `cancellations.csv` | Policy cancellation requests | 20 |
| `commands.txt` | Commands to process, in file order (comment lines start with #) | 113 commands |

## Column reference

Conventions: dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS` (24h, IST, no timezone suffix); money in Rs as plain decimals (no commas, no symbol); percentages as plain numbers (12.5 = 12.5%); booleans `true`/`false`; IDs uppercase with a fixed prefix.

### customers.csv
| column | type | units / format | allowed values | notes |
|---|---|---|---|---|
| customer_id | string | `CUST-nnn` | unique | |
| name | string | | | |
| city | string | | | |
| mobile | string | 10 digits | | |

### policies.csv
| column | type | units / format | allowed values | notes |
|---|---|---|---|---|
| policy_id | string | `POL-nnn` | unique | |
| customer_id | string | | from customers.csv | |
| category | string | | TV, AC, FRIDGE | picks the rate table |
| product_price | decimal | Rs | | basis for premium, payout cap and depreciation |
| product_purchase_date | date | YYYY-MM-DD | | manufacturer warranty = 12 months from this date (same calendar day); coverage starts the next day |
| plan_years | integer | years | 1, 2, 3 | coverage end = coverage start + plan_years×12 months − 1 day |
| policy_purchase_date | date | YYYY-MM-DD | | days after product purchase decide STANDARD / 1.5× / NOT_SOLD |

### claims.csv
| column | type | units / format | allowed values | notes |
|---|---|---|---|---|
| claim_id | string | `CLM-nnn` | unique | |
| policy_id | string | | from policies.csv | |
| claim_date | date | YYYY-MM-DD | | policy year = 12-month block counted from coverage start |
| repair_estimate | decimal | Rs | | compared with 60% of depreciated value |
| fault_type | string | | PANEL, PCB, BACKLIGHT, POWER_SUPPLY, SPEAKER, COMPRESSOR, GAS_LEAK, FAN_MOTOR, SENSOR, THERMOSTAT, DOOR_SEAL, PHYSICAL_DAMAGE, LIQUID, CONSUMABLE | last three are EXCLUDED |

### cancellations.csv
| column | type | units / format | allowed values | notes |
|---|---|---|---|---|
| cancel_id | string | `CAN-nnn` | unique | |
| policy_id | string | | from policies.csv | |
| cancel_date | date | YYYY-MM-DD | | months remaining = complete months from cancel_date to coverage end (cancel inside the last month → 0) |

## Command file format

One command per line, `COMMAND_NAME|arg1|...`; lines starting with `#` are comments. Commands must be processed in file order (claims and cancellations are interleaved chronologically).

| command | arguments | meaning |
|---|---|---|
| `LOAD_POLICIES` | file | price every policy and set cover dates |
| `CLAIM` | claim_id | decide that claim (claims.csv) |
| `CANCEL` | cancel_id | process that cancellation (cancellations.csv) |
| `PRINT_POLICY_REGISTER` | as-of date | print the register |
| `PRINT_CLAIMS_REPORT` | as-of date | print the settlement report |

## Planted scenarios

Every edge case in the brief (EC1…) plus extra traps (TRAP1…). Line numbers count the header as line 1.

- **EC1** – Policy bought exactly 30 days and exactly 11 months after product purchase — 30 days → standard rate; 11 months to the day → 1.5× rate (still sold) → `policies.csv` line 118 (POL-117); `policies.csv` line 146 (POL-145)
- **EC2** – Claim on the first day of coverage and the day before coverage starts — coverage starts the day after the 12-month manufacturer warranty ends (product purchase + 12 months = last warranty day) → `claims.csv` line 21 (CLM-020); `claims.csv` line 30 (CLM-029)
- **EC3** – Fourth claim in a policy year — fourth claim in coverage year 2 of an 80000 TV → rejected (claims 1–3 admitted, deductible from the 2nd) → `claims.csv` line 55 (CLM-054); `claims.csv` line 77 (CLM-076)
- **EC4** – Repair estimate exactly 60% of depreciated value — AC 50000 bought 2024-06-15, claim 2026-08-01 → 2 completed years, DV 40000, estimate 24000.00 = 60% → REPAIR (not exceeding) → `claims.csv` line 62 (CLM-061)
- **EC5** – Cancellation in the final month with zero months remaining — cancelled 10 days before coverage end → 0 months remaining → refund 0 → `cancellations.csv` line 20 (CAN-019)
- **TRAP1** – policy bought 31 days after product purchase → 1.5× rate → `policies.csv` line 124 (POL-123)
- **TRAP2** – policy bought 11 months + 1 day after purchase → NOT_SOLD; a claim against it must be rejected → `policies.csv` line 143 (POL-142); `claims.csv` line 80 (CLM-079)
- **TRAP3** – 3 claims in coverage year 1 then a claim 4 days into year 2 → admitted, counters reset, no deductible → `claims.csv` line 19 (CLM-018)
- **TRAP4** – estimate 24001.00 (just above 60% of DV) → REPLACEMENT paying 40000, policy CLOSED → `claims.csv` line 63 (CLM-062)
- **TRAP5** – claim on a policy already CLOSED by a replacement → `claims.csv` line 44 (CLM-043); `claims.csv` line 75 (CLM-074)
- **TRAP6** – claim one day after coverage end → OUT_OF_COVER → `claims.csv` line 15 (CLM-014)
- **TRAP7** – cancellation after an admitted claim → no refund → `cancellations.csv` line 13 (CAN-012)
- **TRAP8** – cancellation before coverage has started (all months remaining) — brief is silent; document your choice → `cancellations.csv` line 18 (CAN-017)
- **TRAP9** – payout cap: three repairs each below 60% of DV whose total exceeds product price — third payout limited to the remaining amount → `claims.csv` line 82 (CLM-081); `claims.csv` line 79 (CLM-078)

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.

## Output format expected at evaluation

**`policy_register.csv`** — one row per policy in policies.csv order:
`policy_id, customer_id, category, product_price, plan_years, days_after_purchase, pricing_band, rate_pct, premium_before_gst, gst, premium_total, coverage_start, coverage_end, status`
- pricing_band = STANDARD / LOADED_1_5X / NOT_SOLD; status = ACTIVE / CLOSED / CANCELLED / NOT_SOLD / EXPIRED (coverage end before the as-of date).

**`claims_report.csv`** — one row per CLAIM command in command order:
`claim_id, policy_id, claim_date, policy_year, fault_type, repair_estimate, depreciated_value, decision, reason, deductible, payout, claims_remaining_in_year, payout_remaining_in_year`
- decision = REPAIR / REPLACEMENT / REJECTED; reason = OUT_OF_COVER, EXCLUDED, CLAIM_LIMIT, POLICY_CLOSED, NOT_SOLD or blank.

**`cancellation_report.csv`** — one row per CANCEL command:
`cancel_id, policy_id, cancel_date, total_months, months_remaining, refund_before_admin, admin_charge, refund, reason` (reason = CLAIM_ADMITTED when refund is denied).
