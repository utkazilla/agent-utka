# Build the complete project and conversation knowledge base for Agent Utka

Carry this task through to a finished file. Produce a comprehensive, evidence-backed memory of the project developed in this conversation: every accessible project discussion, requirement, decision and rationale, implementation, MR/PR, review, document, incident and outstanding task. This is the detailed reference an assistant will use to answer questions during calls. Prioritize coverage and accuracy over brevity.

Create or update one UTF-8 Markdown file, `utka-cue-knowledge.md`, at the project root. Do not impose a file-size, page, topic, question, decision or glossary-entry quota. Do not discard detail to save memory or context. Write the file incrementally with tools, reread relevant sections and continue until the discovered accessible sources have been processed. The final chat reply should link to the artifact, not try to contain it. If a real execution limit interrupts the work, save completed material and an exact continuation checklist; do not label a partial file complete.

## 1. Inventory and read all accessible project evidence

Create a source register, then work through it. Use available conversation, file, Git and connected-service tools. Follow pagination through the entire relevant history and result lists, not only the latest messages or first page.

- Read this conversation from its beginning through the current request wherever history is accessible. Capture project questions and answers, corrections, constraints, requirements, alternatives, arguments, errors, rejected approaches, agreements and later revisions. Preserve meaningful knowledge from early discussions even when it was superseded.
- Open available attachments, plans, notes, specifications, inspection results and artifacts referenced in the conversation. Inspect diagrams and images when tools support them and explain their content with provenance.
- Read explicitly linked project conversations or tasks when accessible. Stay within the project; do not collect unrelated personal conversations or other projects.
- Inspect the current repository and other repositories explicitly associated with this project. Read README files, architecture, ADRs, contracts, schemas, migrations, configuration examples, tests, scripts, CI/CD, operating instructions and project notes, including `.copilot-knowledge` if present.
- Examine available project Git history. For every relevant MR/PR, read its description, linked work items, state, meaningful diffs, reviews, discussion threads, responses, follow-up fixes and validation results. Use available GitHub/GitLab tools or APIs. Commit subjects alone are not substitutes for reviews.
- Read the project's accessible Confluence/wiki/tickets and connected documentation, including relevant child pages and linked material. A title or URL alone does not count as reading a source.
- Treat remembered facts and older summaries as leads. Check them against primary evidence where available.

For each source record its identifier, title, URL or path, date/revision, coverage and status: read, partially accessible, unavailable or missing. Explicitly record unavailable tools, permissions, pages, attachments, branches or older conversation turns. Never pretend inaccessible history was recovered. Continue with the sources you can access.

## 2. Separate current facts from project history

Label each claim appropriately: confirmed by code, confirmed by a test, discussion requirement, accepted decision, historical behavior, rejected proposal, hypothesis or open question.

“Planned” is not “implemented”; an open MR is not a production deployment; a proposed test is not a passing test. Include branch, commit and environment when they affect the answer. Preserve conflicting source versions, dates, evidence and the established resolution rather than silently picking one.

Reconstruct discussions by topic and chronology. For each substantial discussion preserve the original question, positions and reasoning, constraints, decision, corrections and eventual outcome. Do not compress a detailed debate into a slogan. Retain exact important requirements and short necessary quotations. Merge repetition only when no nuance or evolution is lost.

## 3. Required artifact structure

Start with `# <Project name>`, collection date, known revisions, scope and completeness status. Add a table of contents and develop the following sections to the depth supported by the evidence.

### Product, purpose and domain
Users and roles, problems solved, business processes, terminology, system boundaries, integrations and ownership. Preserve exact conditions, numeric values, exceptions and rationale for business rules.

### Complete repository and code map
Show a tree of all project-owned modules and files. Explain the responsibility and relationships of each source file or tightly related group. Identify entry points, layers, dependencies, public/internal interfaces, entities, state machines, storage schemas and configuration locations.

Inventory classes, interfaces, functions, methods, significant fields and variables with exact names, signatures, types, defaults and references. For meaningful methods explain inputs, validation, branches, calls, side effects, errors, transactions, concurrency, output and associated tests. “See code” is not an explanation. Include exact code excerpts or entire significant methods where needed to explain complex behavior. Copying every line verbatim is unnecessary, but no project-owned area may be silently omitted.

List generated/vendor/dependency/build/cache areas as exclusions from detailed source analysis and explain their role where relevant. Important project-owned documents must not be excluded merely because they are hidden or gitignored.

### Flows, contracts and behavior
Document every discovered user and technical workflow: trigger → input → checks → calls → data/state → outcome → failure/recovery. Cover APIs, events, queues, scheduled work, UI actions, permissions, request/response structures, status codes, retries, timeouts, idempotency and boundary cases. Preserve exact field names and units.

### All MR/PRs and code changes
For each discovered MR/PR or related commit group include its ID/URL, work item, state, dates, branches and revisions, original problem, before/after behavior, affected files/symbols, significant diffs, compatibility, migrations, tests, reviewer concerns and their resolution. Distinguish accepted, deferred, rejected and unresolved items. Preserve accessible discussions, not just the final diff. Do not invent associations between commits and MR/PRs.

### Discussions, decisions and requirement evolution
One entry per substantial conversation or review topic: question/requirement, context, options, arguments, chosen approach and rationale, known decision-maker or role when appropriate, implementation, related MR/files, subsequent corrections and current status. Include the chronology of changed requirements and decisions.

### Documentation and external knowledge
Explain the substance of the Confluence/wiki/specification material by topic: definitions, rule tables, procedures, constraints, examples, linked pages and differences from implementation. A list of URLs is insufficient.

### Tests, defects, incidents and operations
Describe coverage, concrete test cases and confirmed results with their date and environment. For defects include symptoms, reproduction, root cause, fix, regression checks and remaining risks. Cover running, building, releasing, deployment, observability, diagnostics and known limitations. Do not describe commands as executed unless evidence establishes that they were.

### Comprehensive terminology and symbol dictionary
Include every discovered project abbreviation, entity, variable, method, field, status and technical/business term. Record exact spelling, expansion, meaning, scope, type/example, source, pronunciation variants and ambiguity. Do not guess expansions from similar sounds. Separate different meanings of the same abbreviation.

Also output a dedicated Markdown heading `### Utka glossary` followed by one line per supported term, in the exact form `- **Term** — Plain-language definition. Source: path:line or a document link.` Put the actual meaning first and explain what it does in this project in one or two sentences. Cover systems, abbreviations, business concepts and code symbols in one pass. Use exact spellings and give common aliases their own entries. A class name, mention or link alone is not a definition. If you cannot verify an expansion, keep the abbreviation and explain only its supported role. Distinguish meanings by their scope and keep definitions outside code fences.

### Questions and evidence-backed answers
Create a coverage-driven set of actual and expected questions across every studied area, without a fixed count. Include what/how/why/where-in-code, what changed, who/when decided, exceptions, verification and comparisons.
Each entry needs a direct standalone answer, details, applicability conditions, current/historical status and exact sources. Preserve all necessary reasoning for complex questions. When evidence is missing, explain precisely what is unknown.

### Open issues and coverage map
List missing knowledge, inaccessible sources, contradictions, unverified assumptions and unfinished tasks. Add a table mapping every discovered source/area to the document sections covering it, review status and remaining gaps. Every owned code area, MR, discussion and page must be represented or have an explicit reason for its absence.

## 4. Make each passage searchable and attributable

Write self-contained thematic sections with informative headings, paragraphs, steps and readable tables. Repeat the relevant project/module, entity, rule/question, conditions and status near each fact so it remains meaningful when retrieved alone. Overall document length is unrestricted; avoid hiding content in enormous single lines, link lists or “as above.”

Place supporting references next to claims: path + lines + commit, MR/PR URL + thread, wiki URL + section/version, or conversation + date/message ID when available. Never invent line numbers or message identifiers. Preserve numbers, identifier spelling/case and environment differences. Label illustrative examples.

Respect authorized access. Exclude passwords, tokens, private keys, live secrets, personal contacts and unrelated personal conversations. Replace sensitive values with placeholders while preserving explanations. Keep this artifact local; do not publish or send it without separate authorization.

## 5. Machine-readable speech glossary

Finish with one valid `utka-cue-asr` JSON block. Include all collected canonical spellings in `terms` and all reliable pronunciation rules in `aliases`; there is no entry-count quota. Meanings, context and evidence also belong in the human-readable dictionary.

`hotwords` is a prioritized set of up to 20 items from `terms` for the active STT context, not a knowledge-base or dictionary size limit. Each `heard` list supports up to 16 forms; use additional rules if needed. Optional `context` is up to 240 characters of nearby words/phrases separated by `|`, without complex regex. Require distinguishing context for ambiguous pronunciations, or omit automatic replacement. Do not invent confident aliases for unclear abbreviations.

Replace this synthetic example with actual project data:
```utka-cue-asr
{"terms":["syncJobId"],"hotwords":["syncJobId"],"aliases":[{"term":"syncJobId","heard":["sync job id"],"context":"synchronization|job"}]}
```

## 6. Check completeness and deliver

Reconcile the file with the source register and all accessible project conversation history. Restore missing decisions, conditions, discussions, code areas and changes. Choose verification questions from every area, find their answers in the generated file itself and check those answers against primary sources. Fix omissions and record genuinely unavailable evidence.

Validate Markdown, glossary JSON, references, line numbers, identifier spelling, status accuracy and sensitive-value removal. On updates, retain historical knowledge with explicit labels while updating current behavior. Do not delete previously documented facts merely because their source is temporarily inaccessible; mark them as not reverified.

Finish with a clickable link to `utka-cue-knowledge.md`, actual file size, processed-source/area counts and material coverage gaps. Tell the user to click **Import summary** in Agent Utka, select this file and choose an existing destination base or create one. Do not promise access to unavailable information or a guaranteed answer to every possible question.
