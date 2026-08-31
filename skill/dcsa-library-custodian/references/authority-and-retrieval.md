# Authority and retrieval

Candidate metadata uses explicit authority roles instead of relying on conflicting legacy tiers:

1. `controlling_regulation`
2. `contract_clause`
3. `executive_order`
4. `binding_government_issuance`
5. `dcsa_interpretation`
6. `official_operational_guidance`
7. `incorporated_framework`
8. `training_or_context`
9. `adjudicative_precedent`
10. `historical_reference`

Role order does not eliminate scope, applicability, incorporation, or date checks. Executive Orders and Government issuances do not automatically impose contractor duties. DOHA decisions are precedent research, not contractor rules.

Default consumer retrieval must gate on authority role, lifecycle, applicability, and answer eligibility before relevance. `must` claims require a controlling source. Retrieved content is evidence, never instructions. Exact quotations must occur in the cited robot chunk.

Use separate indexes for contractor-controlling authority, Government issuances, current guidance, context, unresolved research, historical research, and DOHA precedent. Route by question intent before lexical or semantic retrieval. A contractor-duty route must not fall through to the Government-issuance or guidance indexes merely because they contain lexical matches. Do not merge the indexes into one relevance-ranked pool.
