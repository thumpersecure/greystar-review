# Entry schema (one JSON object per entry; seed files are JSON arrays)
{
  "id": "kebab-slug-unique",            // e.g. "ftc-colorado-v-greystar-2025"
  "date": "YYYY-MM-DD",                 // date of the event/article (YYYY-MM or YYYY ok if unknown day)
  "title": "Plain factual headline",
  "category": "lawsuit|regulator|news|tenant",
  "subject": ["greystar"] or ["bob-faith"] or both,
  "location": "City, ST" or "Nationwide",
  "property": "Building name or empty string",
  "outlet": "Court / agency / publication / review site",
  "url": "https://primary-source (must load or be a real known URL)",
  "archive_url": "https://web.archive.org/... or empty string",
  "summary": "1-3 neutral sentences. Allegations stated as allegations. Outcome if known.",
  "status": "e.g. settled $24M / pending / dismissed / published"
}
Rules: every entry needs a real primary-source URL you actually verified (fetched or confirmed via search result showing that URL). No invented URLs. If unverifiable, omit it. Allegations = "alleged"/"according to". No private individuals' contact info; tenant reviewers by first name/initial only.
Wording rule: never use "approve", "approved", "approval" or "approving" in any title, summary or status (say "court finalized", "pending before the court", "final fairness hearing", "signs off").
