# APRS V5 Master Winning Product Discovery & Quantitative Evaluation Dossier

**Evaluated by:** NVIDIA Nemotron Super 120B (`nvidia/nemotron-3-super-120b-a12b`) + APRS V5 Decision Arbiter Engine
**Date:** 2026-08-28 20:45:01

---

## Product PROD_01: Hydro-Sonic Fruit, Veg & Meat Purifier (Hydroxyl Electrolysis)

We need to compute financials.

Given:

Base Factory COGS: $5.8
Packaging & Inserts: $1.5
Shipping DDP: $2.4

Landed COGS = sum = 5.8 + 1.5 + 2.4 = $9.7

Planned Retail MSRP: $54.99

Gross Margin = MSRP - Landed COGS = 54.99 - 9.7 = $45.29

Gross Margin % = Gross Margin / MSRP *100 = 45.29/54.99 ≈ 0.8235 => 82.35%

Now other costs: Estimated CAC: $16.0
Platform/Payment Fee: 5.0% of MSRP? Usually fee on sale price. So fee = 0.05 * 54.99 = $2.7495 ≈ $2.75
Estimated Return Rate: 4.0% => cost of returns? Usually cost of goods lost plus maybe restocking? We'll assume return cost = Landed COGS * return rate = 9.7 * 0.04 = $0.388 ≈ $0.39. Could also include shipping cost of return but not given. We'll use that.

Net Profit per unit = Gross Margin - CAC - Platform Fee - Return Cost

= 45.29 - 16.0 - 2.75 - 0.39 = 26.15 (approx). Let's compute precisely: 45.29 - 16 = 29.29; minus 2.75 = 26.54; minus 0.39 = 26.15.

Net Profit % = Net Profit / MSRP *100 = 26.15/54.99 ≈ 0.4755 => 47.55%

Margin Multiplier = MSRP / Landed COGS = 54.99 / 9.7 ≈ 5.669

Break-even ROAS: ROAS needed to cover CAC? Usually break-even ROAS = (CAC + other variable costs?) Actually break-even ROAS = (CAC) / (Gross Profit per sale?) Wait typical: ROAS = Revenue / Ad Spend. Break-even when profit = 0: Revenue * (1 - fee - return%) - COGS - CAC = 0. Solve for ROAS = Revenue / Ad Spend. Let ad spend = CAC per unit? Actually CAC is cost to acquire a customer, which is ad spend per conversion. So break-even ROAS = (MSRP) / CAC? Not exactly because need to cover COGS etc. Usually break-even ROAS = (COGS + other costs) / (MSRP * (1 - fee - return%)). But we can compute needed revenue per ad spend to break even: Let ad spend = CAC. Profit = Revenue*(1 - fee - return%) - COGS - CAC. Set =0 => Revenue = (COGS + CAC) / (1 - fee - return%). Then ROAS = Revenue / CAC = (COGS + CAC) / (CAC * (1 - fee - return%)). Compute: COGS=9.7, CAC=16, fee=0.05, return=0.04 => (1 - fee - return) = 0.91. Numerator = 9.7+16=25.7. Denominator = 16*0.91 = 14.56. ROAS = 25.7/14.56 = 1.765. So break-even ROAS ≈ 1.77.

Now stress test scenarios.

Base net profit per unit = $26.15, net margin % = 47.55%.

Scenario A: CAC +40% => CAC = 16 *1.4 = $22.4. Recalc net profit: Gross margin 45.29 - CAC 22.4 - fee 2.75 - return cost 0.39 = 45.29 - 25.54 = 19.75. Net margin % = 19.75/54.99 = 0.359 = 35.9%.

Scenario B: Returns 15% => return cost = 9.7 *0.15 = 1.455. Net profit = 45.29 -16 -2.75 -1.455 = 25.085. Net margin % = 25.085/54.99 = 0.456 = 45.6%.

Scenario C: Fees +5% => fee becomes 10%? Actually base fee 5%; +5% means fee = 10% of MSRP = 5.499. Net profit = 45.29 -16 -5.499 -0.39 = 23.401. Net margin % = 23.401/54.99 = 0.4255 = 42.6%.

Scenario D: Freight +20% => shipping DDP increases 20%: base shipping 2.4 *1.2 = 2.88. So landed COGS = 5.8+1.5+2.88 = 10.18. Gross margin = MSRP - landed COGS = 54.99 -10.18 = 44.81. Net profit = 44.81 -16 -2.75 - (return cost based on new COGS? return cost = landed COGS *0.04 = 10.18*0.04=0.4072). So net profit =44.81 -16 -2.75 -0.407 = 25.653. Net margin % = 25.653/54.99 =0.4665 =46.7%.

Combined Stress: apply all four simultaneously? Likely combine worst-case: CAC +40%, Returns 15%, Fees +5%, Freight +20%. Compute.

CAC = 22.4
Fee = 10% of MSRP = 5.499
Freight increased => shipping 2.88 => landed COGS = 5.8+1.5+

---

## Product PROD_02: Dynamic Inflatable Lumbar Decompression Stretcher with Red Light Therapy

We need to compute financials.

Given:

Base Factory COGS: $11.2
Packaging & Inserts: $2.1
Shipping DDP: $4.2

Landed COGS = 11.2 + 2.1 + 4.2 = $17.5

MSRP = $89.99

Gross Margin = MSRP - Landed COGS = 89.99 - 17.5 = $72.49

Gross Margin % = 72.49 / 89.99 = approx 0.8055 = 80.55%

Now Net Profit: subtract CAC, Platform/Payment Fee (5% of MSRP?), Return Rate (5% of revenue?), maybe also other costs? Typically net profit = MSRP - Landed COGS - CAC - (Platform Fee * MSRP) - (Return Rate * MSRP * MSRP). Return cost: assume refund of revenue plus maybe restocking cost? We'll approximate as lost revenue = Return Rate * MSRP.

Platform/Payment Fee = 5% of MSRP = 0.05 * 89.99 = $4.4995 ≈ $4.50

Return Rate = 5% of MSRP = 0.05 * 89.99 = $4.4995 ≈ $4.50 (lost revenue)

CAC = $26.0

Net Profit = MSRP - Landed COGS - CAC - PlatformFee - ReturnLoss

= 89.99 - 17.5 - 26.0 - 4.5 - 4.5 = 89.99 - 52.5 = 37.49? Wait compute: 17.5+26=43.5; +4.5+4.5=52.5; 89.99-52.5=37.49.

Net Profit % = Net Profit / MSRP = 37.49 / 89.99 = 0.4166 = 41.66%

Margin Multiplier = MSRP / Landed COGS = 89.99 / 17.5 = approx 5.142

Break-even ROAS: ROAS needed to cover CAC? Usually break-even ROAS = (Landed COGS + CAC + Fees + ReturnLoss) / (MSRP * (1 - Fees - ReturnRate? Actually ROAS = Revenue / Ad Spend. Break-even when profit =0: Revenue * (1 - Fees - ReturnRate) - COGS - CAC =0. Solve for ROAS = Revenue / Ad Spend. Ad Spend = CAC per unit? Actually CAC is cost to acquire a customer, which is ad spend per conversion. So break-even ROAS = (Landed COGS + Fees*MSRP + ReturnLoss) / (MSRP * (1 - Fees - ReturnRate))? Let's derive.

Let Rev = MSRP per unit. Ad Spend = CAC. Fees = f*Rev (platform fee). Return loss = r*Rev (lost revenue). COGS = c.

Profit = Rev - c - CAC - f*Rev - r*Rev = Rev*(1 - f - r) - c - CAC.

Set profit=0 => Rev*(1 - f - r) = c + CAC => Rev = (c + CAC) / (1 - f - r). Then ROAS = Rev / CAC = (c + CAC) / (CAC * (1 - f - r)).

Plug numbers: c=17.5, CAC=26, f=0.05, r=0.05 => 1 - f - r = 0.9.

c + CAC = 17.5 + 26 = 43.5.

Rev needed = 43.5 / 0.9 = 48.333... Actually that's revenue needed per unit to break even after fees and returns? Wait Rev is MSRP; we solve for required MSRP? Actually we treat Rev as variable; but we have fixed MSRP. So break-even ROAS = (c + CAC) / (CAC * (1 - f - r)) = 43.5 / (26 * 0.9) = 43.5 / 23.4 = 1.859. So need ROAS ~1.86.

Alternatively simpler: break-even ROAS = (Landed COGS + CAC) / (CAC * (1 - Fee% - Return%)) = as above.

We'll present.

Now 4-Scenario Stress Test Matrix.

Base net margin % = Net Profit / MSRP = 41.66%.

We need to adjust each scenario and compute net margin %.

Scenario A: +40% CAC => CAC_new = 26 * 1.4 = 36.4

Other costs same.

Net Profit_A = MSRP - LandedCOGS - CAC_new - Fee - ReturnLoss

Fee and ReturnLoss same as base (5% each of MSRP) = 4.5 each.

Compute: 89.99 - 17.5 - 36.4 - 4.5 - 4.5 = 89.99 - 62.9 = 27.09

Net margin %_A = 27.09 / 89.99 = 0.301 = 30.1%

Scenario B: Returns 15% (instead of 5%). So ReturnLoss = 0.15 * MSRP = 13.4985 ≈ $13.50

CAC base 26, Fee 5% = 4.5

Net Profit_B = 89.99 - 17.5 - 26 - 4.5 - 13.5 = 89.99 - 61.5 = 28.49

Margin %_B = 28.49 / 89.99 = 0.3166 = 31.7%

Scenario C: +5% Fees (i.e., fee increases from 5% to 10%?). Actually +5% Fees meaning fee becomes 10%? Or increase by 5 percentage points. We'll assume fee becomes 10% of MSRP.

Fee_C = 0.10 * 89.99 = 8.999 ≈ $9.00

ReturnLoss base 5% = 4.5



---

## Product PROD_03: Ultra-Quiet Sub-48dB Vacuum Pet Groomer & Anti-Shedding Kit (2.5L Cyclone)

We need to compute financials.

Given:

Base Factory COGS: $18.5
Packaging & Inserts: $3.8
Shipping DDP: $6.5

Landed COGS = 18.5 + 3.8 + 6.5 = $28.8

MSRP = $129.99

Gross Margin = MSRP - Landed COGS = 129.99 - 28.8 = $101.19

Gross Margin % = 101.19 / 129.99 = approx 0.778 = 77.8%

Now Net Profit: subtract CAC, Platform/Payment Fee (5% of MSRP?), and Returns (estimated return rate 6% of revenue? Usually net profit after returns: revenue * (1 - return rate) minus costs? Let's assume net profit per unit = (MSRP * (1 - return rate)) - Landed COGS - CAC - (Platform Fee % * MSRP). Or we could compute net profit after fees and returns.

Given: Estimated CAC: $38.0
Platform/Payment Fee: 5.0% (presumably of sale price)
Estimated Return Rate: 6.0% (so we lose revenue and maybe also incur restocking cost? We'll assume lost revenue only.)

Thus effective revenue per unit = MSRP * (1 - Return Rate) = 129.99 * 0.94 = $122.1906

Platform fee = 5% of MSRP? Usually of transaction amount (sale price). We'll apply to MSRP: 0.05 * 129.99 = $6.4995

Net profit = effective revenue - Landed COGS - CAC - Platform fee

= 122.1906 - 28.8 - 38.0 - 6.4995 = 48.8911? Let's compute: 122.1906 - 28.8 = 93.3906; minus 38.0 = 55.3906; minus 6.4995 = 48.8911.

Net profit % = Net profit / MSRP? Or / effective revenue? Usually net margin = net profit / revenue (post-return). We'll compute net margin % = Net profit / (MSRP * (1 - Return Rate)) = 48.8911 / 122.1906 = 0.4 = 40.0% approx.

Alternatively net profit % of MSRP = 48.8911 / 129.99 = 0.376 = 37.6%.

We'll present both.

Margin Multiplier = MSRP / Landed COGS = 129.99 / 28.8 = 4.514 approx.

Break-even ROAS: ROAS needed to cover CAC? Usually break-even ROAS = (Landed COGS + CAC + Platform fee) / (MSRP * (1 - Return Rate))? Actually ROAS = Revenue / Ad Spend. Break-even when profit = 0: Revenue * (1 - return) - COGS - CAC - fee = 0 => Revenue = (COGS + CAC + fee) / (1 - return). Then ROAS = Revenue / CAC. So break-even ROAS = ((COGS + CAC + fee) / (1 - return)) / CAC.

Compute: COGS+ CAC + fee = 28.8 + 38.0 + 6.4995 = 73.2995

Divide by (1 - return) = 0.94 => 73.2995 / 0.94 = 78.0? Let's compute: 73.2995 / 0.94 = 78.0 approx (73.2995/0.94 = 78.0 exactly? 0.94*78 = 73.32 close). So required revenue ~ $78.0.

Then ROAS = revenue / CAC = 78.0 / 38.0 = 2.0526. So break-even ROAS ~2.05.

Now stress test matrix.

Scenario A: +40% CAC => CAC = 38 * 1.4 = 53.2

Scenario B: Returns 15% (instead of 6%)

Scenario C: +5% Fees => fee = 5% +5% =10% of MSRP? Actually increase by 5 percentage points? Likely fee increases from 5% to 10% (i.e., +5% absolute). We'll treat as fee = 10% of MSRP.

Scenario D: +20% Freight => shipping DDP increase 20%: base shipping 6.5 *1.2 = 7.8

We need Combined Stress Net Margin % (does it stay >10%?). Combined stress means apply all four scenarios simultaneously? Likely yes.

So compute under combined stress:

- CAC = 53.2
- Returns = 15%
- Fee = 10%
- Shipping = 7.8 (instead of 6.5)

Landed COGS = base COGS 18.5 + packaging 3.8 + shipping 7.8 = 30.1

Effective revenue = MSRP * (1 - return) = 129.99 * 0.85 = 110.4915

Platform fee = 10% of MSRP = 12.999

Net profit = effective revenue - Landed COGS - CAC - fee

= 110.4915 - 30.1 - 53.2 - 12.999 = 14.1925? Let's compute: 110.4915 -30.1 = 80.3915; minus 53.2 = 27.1915; minus 12.999 = 14.1925.

Net margin % = net profit / effective revenue = 14.1925 / 110.4915 = 0.1284 = 12.8%

Thus >10% so passes.

Now Gap Scoring Matrix: Need to score 1-5 on each gap, then weighted score /25? Actually they

---

## Product PROD_04: 120,000 RPM Cordless Cyclone Car Air Duster & Crevice Vacuum 2-in-1

We need to compute financials.

Given:
Base Factory COGS: $9.8
Packaging & Inserts: $2.4
Shipping DDP: $3.6
Landed COGS = sum = 9.8+2.4+3.6 = $15.8

Planned Retail MSRP: $69.99

Gross Margin = MSRP - Landed COGS = 69.99 - 15.8 = $54.19
Gross Margin % = 54.19 / 69.99 = approx 0.7745 => 77.45%

Now other costs: Estimated CAC: $20.0
Platform/Payment Fee: 5.0% of MSRP? Usually fee on sale price. So fee = 0.05 * 69.99 = $3.4995 ~ $3.50
Estimated Return Rate: 4.0% => cost of returns? Usually you lose revenue and maybe COGS? For net profit, we can subtract expected loss: Return rate * (MSRP - maybe some restocking?). Simplify: expected loss = Return Rate * MSRP = 0.04 * 69.99 = $2.7996 ~ $2.80 (lost revenue). Also you may have to refund and maybe restock cost? We'll just subtract that.

Net Profit = Gross Margin - CAC - Platform Fee - Expected Return Loss
= 54.19 - 20.0 - 3.50 - 2.80 = $27.89

Net Profit % = Net Profit / MSRP = 27.89 / 69.99 = 0.3985 => 39.85%

Margin Multiplier = MSRP / Landed COGS = 69.99 / 15.8 = approx 4.43

Break-even ROAS: ROAS needed to cover CAC? Usually break-even ROAS = (CAC) / (Gross Profit per sale)? Actually ROAS = Revenue / Ad Spend. To break even, revenue from ad spend must cover CAC + other costs? Usually break-even ROAS = (CAC) / (Gross Margin)?? Let's compute: To break even on ad spend, the gross profit from a sale must equal CAC. So required revenue such that gross profit = CAC. Gross profit per sale = Gross Margin = $54.19. So if we spend X on ads, we need gross profit >= X. So break-even ROAS = Revenue / Ad Spend = MSRP / CAC? Actually if we spend $1 on ads, we need to generate revenue such that gross profit covers that $1. Gross profit per $ of revenue = Gross Margin % = 0.7745. So to get $1 gross profit, need revenue = $1 / 0.7745 = $1.291. So ROAS = revenue / ad spend = 1.291. Alternatively break-even ROAS = 1 / Gross Margin % = 1 / 0.7745 = 1.29. We'll present that.

Now stress test matrix.

Scenario A: +40% CAC => CAC = 20 * 1.4 = $28.0
Scenario B: 15% Returns => Return loss = 0.15 * 69.99 = $10.4985 ~ $10.50
Scenario C: +5% Fees => Fees = 5% +5% =10% of MSRP? Actually base fee 5%; increase by 5 percentage points => 10% fee. So fee = 0.10 * 69.99 = $6.999 ~ $7.00
Scenario D: +20% Freight => Shipping DDP increase 20%: base shipping $3.6 *1.2 = $4.32. So landed COGS changes: packaging same, factory same, shipping increased.

We need to compute net margin % for each scenario individually? Then combined stress net margin % (apply all stressors together?) and see if >10%.

Let's compute baseline net profit we had: $27.89, net margin % = 39.85%.

Now scenario A: CAC $28.0, other costs same (fees 3.5, returns 2.8). Gross margin unchanged 54.19. Net profit = 54.19 - 28.0 - 3.5 - 2.8 = $19.89. Net margin % = 19.89 / 69.99 = 0.2842 => 28.4%

Scenario B: Returns 15% => loss = 10.50. Others same: CAC 20, fees 3.5. Net profit = 54.19 -20 -3.5 -10.5 = $20.19. Net margin % = 20.19/69.99=0.2885 =>28.9%

Scenario C: Fees 10% => fee = 7.00. Others same: CAC20, returns2.8. Net profit = 54.19 -20 -7.0 -2.8 = $24.39. Net margin % = 24.39/69.99=0.3485 =>34.9%

Scenario D: Shipping +20% => shipping 4.32. Landed COGS = 9.8+2.4+4.32 = $16.52. Gross margin = 69.99 -16.52 = $53.47. Others same: CAC20, fees3.5, returns2.8. Net profit = 53.47 -20 -3.5 -2.8 = $27.17. Net margin % = 27.17/69.99=0.3882 =>38.8%

Now combined stress: apply all four stressors together: CAC +40% =>28.0, Returns 15% =>10.5, Fees +5% =>10% fee =>7.0, Shipping +20% =>4.32 shipping. Landed COGS = 9.8+2.4+4.32 =16.52. Gross margin = 69.99-16.

---

## Product PROD_05: Magnetic Solid Brass & Walnut Precision Safety Razor System with Alignment

We need to compute financials.

Given:

Base Factory COGS: $4.5
Packaging & Inserts: $2.2
Shipping DDP: $1.9

Landed COGS = 4.5 + 2.2 + 1.9 = $8.6

Planned Retail MSRP: $48.0

Gross Margin = MSRP - Landed COGS = 48 - 8.6 = $39.4

Gross Margin % = 39.4 / 48 = 0.8208 = 82.1%

Now net profit: subtract CAC, platform/payment fee, returns cost? Usually net profit = Gross Margin - CAC - (Platform Fee * MSRP) - (Return Rate * MSRP?) Actually returns cost includes refund of revenue and maybe restocking? We'll assume returns cost = Return Rate * MSRP (lost revenue). So net profit = Gross Margin - CAC - Platform Fee% * MSRP - Return Rate% * MSRP.

Platform Fee: 5.0% of MSRP = 0.05 * 48 = $2.4

Estimated Return Rate: 3.0% of MSRP = 0.03 * 48 = $1.44

CAC: $14.0

Net Profit = 39.4 - 14.0 - 2.4 - 1.44 = 21.56

Net Profit % = Net Profit / MSRP = 21.56 / 48 = 0.4492 = 44.9%

Margin Multiplier = MSRP / Landed COGS = 48 / 8.6 = 5.581 ≈ 5.58

Break-even ROAS: ROAS needed to cover CAC? Usually break-even ROAS = (CAC) / (Gross Profit per sale?) Actually ROAS = Revenue / Ad Spend. Break-even when profit zero: Revenue * (1 - fee - return%) - COGS - CAC = 0. Solve for ROAS = Revenue / Ad Spend. Let Ad Spend = CAC per acquisition? Actually CAC is cost to acquire a customer, which is ad spend per sale. So break-even ROAS = Revenue needed per ad spend to break even. Revenue per sale = MSRP. So break-even ROAS = MSRP / (COGS + Fees + Returns + CAC?) Wait we want ROAS where profit zero: Profit = Revenue - COGS - Fees - Returns - Ad Spend. Set =0 => Ad Spend = Revenue - COGS - Fees - Returns. ROAS = Revenue / Ad Spend = Revenue / (Revenue - COGS - Fees - Returns). Compute denominator: Revenue - COGS - Fees - Returns = 48 - 8.6 - 2.4 - 1.44 = 35.56. So break-even ROAS = 48 / 35.56 = 1.35. Alternatively sometimes they compute break-even ROAS = (COGS + Fees + Returns) / (Revenue - (COGS+Fees+Returns))? No. We'll present as above.

Now stress test matrix.

Scenario A: +40% CAC => CAC = 14 * 1.4 = $19.6

Scenario B: Returns 15% => Return cost = 0.15 * 48 = $7.2

Scenario C: +5% Fees => Platform fee = 5% +5% =10%? Actually +5% absolute? Likely increase fee by 5 percentage points => 5% +5% =10% of MSRP = $4.8

Scenario D: +20% Freight => Shipping DDP increase 20%: 1.9 *1.2 = $2.28

We need Combined Stress Net Margin % (does it stay >10%?). Combined stress means apply all scenarios simultaneously? Likely yes. So compute new values:

CAC = 19.6
Return Rate = 15% => return cost = 7.2
Platform Fee = 10% => fee = 4.8
Shipping = 2.28

Landed COGS = base COGS 4.5 + packaging 2.2 + shipping 2.28 = 8.98

Gross Margin = 48 - 8.98 = 39.02

Net Profit = Gross Margin - CAC - fee - return cost = 39.02 - 19.6 - 4.8 - 7.2 = 7.42

Net Margin % = 7.42 / 48 = 0.1546 = 15.5%

Thus >10% so passes.

We could also compute each scenario individually? The prompt: "4-Scenario Stress Test Matrix: - Scenario A (+40% CAC) - Scenario B (15% Returns) - Scenario C (+5% Fees) - Scenario D (+20% Freight) - Combined Stress Net Margin % (Does it stay > 10%?)". So we need to present each scenario net margin and combined.

Let's compute each scenario net margin individually (others baseline).

Baseline net margin we have 44.9%.

Scenario A: CAC 19.6, others baseline.

Landed COGS = 8.6 (baseline). Gross Margin = 39.4.

Net Profit = 39.4 - 19.6 - 2.4 - 1.44 = 15.96

Net Margin % = 15.96/48 = 0.3325 = 33.3%

Scenario B: Returns 15% => return cost = 7.2

Net Profit = 39.4 - 14 - 2.4 - 7.2 = 15.8

Margin % = 15.8/48 = 0.3292 = 32.9%

Scenario C: Fees +5% => fee = 10% => 4.8

Net Profit = 39.4 -14 -4.8 -1.44 = 19.16

Margin % = 19.16/48 = 0.3992 = 39.9%

Scenario D: Freight +20% => shipping = 2.28

Landed COGS = 4.5+2.2+2.28 = 8.98

Gross Margin = 48 - 8.98 = 3

---

