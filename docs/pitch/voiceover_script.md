# Demo video: four voices, one subtitled video (4:52)

Decided 4 Oct 17:00. P1-Claude recorded the whole video (silent, 1920×1080) on the submission laptop, with **every line
burned in as a subtitle** and a "Layer N · presenter" tag. Each member records **only their voice**, reading the subtitles
exactly while their part plays. The subtitles work as a teleprompter.

**Presenters:** Vansh: Layer 1 · Garv: Layer 2 · Kris: Layer 3 · Anuj: Layer 4. File: `D:/ontrack_work/video/OnTrack_demo_silent.webm`.

**How:** open the video in Clipchamp, play your part, and record audio (Record → Audio) while reading the subtitle on screen.
Start each line when its subtitle appears (times below). Speak calmly, and pause at the end of each line. Then place each voice under its
part in one Clipchamp project, export 1080p, and upload as unlisted YouTube or Google Drive (anyone with the link).

| Starts | Presenter | Line (exactly as on screen) |
|---|---|---|
| 0:01 | Vansh Jaiswal (Layer 1) | In collections, one customer's story is split across five systems. OnTrack joins it up, reads hardship out of notes and calls, and recommends the next best action, with a person always making the call. |
| 0:20 | Vansh Jaiswal (Layer 1) | Layer one turns thirty-one raw tables into one trusted record per customer: a million people, matched blind at 99.8% precision, with eight contract rules and twenty data issues checked on every build. |
| 0:41 | Vansh Jaiswal (Layer 1) | Here is one customer, linked across the card, loan, bank and CRM systems, each with its evidence and confidence. One open case, an auto loan six days late, and OnTrack already recommends a hardship referral. |
| 1:02 | Vansh Jaiswal (Layer 1) | When the matcher is unsure, it doesn't guess. A data steward sees masked evidence and decides, and the next build learns from it. |
| 1:17 | Garv Pratap Singh (Layer 2) | Layer two is Ask. Analysts ask in plain English, and certified metrics answer instantly, with the exact SQL that produced the answer. |
| 1:32 | Garv Pratap Singh (Layer 2) | It also explains decisions. Why was this case referred? The answer comes from the recommendation itself, with its reasons, in under a second. |
| 1:47 | Garv Pratap Singh (Layer 2) | Policy answers cite the section they come from, and they follow the current policy, not an old FAQ. |
| 2:02 | Garv Pratap Singh (Layer 2) | And it refuses what it must: protected attributes, personal data and prompt injection. Twenty-one of twenty-one on our dev benchmark. |
| 2:15 | Kris Jain (Layer 3) | Layer three turns conversations into features. Every note and every call is scored for hardship: 8,883 open cases show hardship that the case flag missed. |
| 2:35 | Kris Jain (Layer 3) | This customer said on a call: my pay got cut in August. The quote is kept as evidence and checked against the transcript it came from. |
| 2:53 | Kris Jain (Layer 3) | All structured features come from one point-in-time function, used for both training and live scoring, so the model never sees the future. |
| 3:11 | Anuj Kumar Tiwari (Layer 4) | Layer four decides the next best action. Rules first: a policy gate with fifty-five tests removes anything not allowed. Then the model ranks what's left, with three plain-English reasons. |
| 3:29 | Anuj Kumar Tiwari (Layer 4) | Blocked actions show the rule behind each one. For hardship there are no calls or texts: a person decides, within one business day. |
| 3:45 | Anuj Kumar Tiwari (Layer 4) | We tested like with like: self-cure AUC 0.83 against 0.72 for the bank's own model, and more than 99% of the cases we'd act on now really didn't pay on their own. |
| 4:03 | Anuj Kumar Tiwari (Layer 4) | On today's book, that's about 157 thousand dollars more in expected payments per round of contacts, valued conservatively. |
| 4:17 | Anuj Kumar Tiwari (Layer 4) | Sixty-two percent of cases go to a person first, and the hardship team can reach every new referral within a business day, highest dollars at risk first. |
| 4:33 | Anuj Kumar Tiwari (Layer 4) | Every decision and its outcome becomes a label for the next model. AI recommends, rules constrain, humans decide, and outcomes improve the next recommendation. |
| 4:45 | Anuj Kumar Tiwari (Layer 4) | Thank you. We're Team HOmiES. |

Recorder: `p1_tools/record_full.py` (P1). Numbers are from the submission build.
