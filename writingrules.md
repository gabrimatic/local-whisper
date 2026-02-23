# Writing Rules

Rules for consistent tone, structure, and style across all projects and documentation.

---

## 1. Voice & Tone

1. **Direct and declarative.** Lead with what the thing is and what it does. No warm-up sentences, no throat-clearing.
2. **Confident without being loud.** State facts plainly. No superlatives, no "revolutionary," no "best-in-class," no "powerful."
3. **Second person, present tense.** "You run it on your devices." Not "users can run it" or "it can be run."
4. **Conversational but technical.** Write like you're explaining to a sharp engineer over coffee. Casual phrasing, precise terminology.
5. **Opinionated with an escape hatch.** State the preferred path clearly ("Preferred setup: X"), then mention alternatives briefly.
6. **No apologies, no hedging.** Don't say "unfortunately," "please note that," or "we're sorry." If there's a limitation, state it as a fact and move on.
7. **Never address the reader as "user" or "developer."** They're "you."
8. **Match formality to depth.** Top of the document is warmer and broader. The deeper you go, the more terse and technical.

---

## 2. Structure & Rhythm

9. **Short paragraphs.** One to three sentences max. White space is a feature.
10. **Lists over prose.** When there are more than two items, use a list. Bullet points, tables, or inline links.
11. **Front-load the point.** The first sentence of any section should tell the reader exactly what they'll get. Details come after.
12. **Big picture first, details cascade.** Overview, then how it works, then subsystems, then per-feature specifics. Zoom in progressively.
13. **Group by concern, not by chronology.** Sections organized by topic ("Security," "Channels," "Tools"), not by sequence ("Step 1," "Step 2").
14. **Respect the reader's time.** Include a TL;DR. Put the quick path first, deep dives later. Label sections so people can skip.
15. **State the default, then the override.** Always tell the reader what happens out of the box before explaining how to change it. "Default behavior: X. To change: Y."
16. **Label what's optional.** If something isn't required, say "(optional)" explicitly. Don't let the reader guess.

---

## 3. Hierarchy & Headings

17. **H2 for major sections, H3 for subsections.** Never skip heading levels. Never use H1 inside the body (that's the title only).
18. **Heading text is a noun phrase or short label.** "Security," "Quick start," "Apps." Not "How to set up security" or "Here's how apps work."

---

## 4. Sentence-Level Patterns

19. **Use parentheticals for context.** Drop clarifications, alternatives, and technical notes in parentheses inline rather than breaking flow with a new sentence.
20. **Semicolons to pack related clauses.** Keeps pace tight without splitting into separate sentences.
21. **Em dashes for asides.** Breaks up dense info without losing momentum. "The gateway is just the control plane — the product is the assistant."
22. **Comma-separated alternatives inline.** "Works with X, Y, or Z." Not a list, not a paragraph. Just slide them in.
23. **"If X, Y" for conditional guidance.** Not "In the event that" or "When you have configured."
24. **Parallel grammatical structure in lists.** All nouns, all verb phrases, or all sentences. Never mix forms within a single list.

---

## 5. Wording & Phrasing

25. **Imperative for instructions.** "Run this." "Set this." Not "you should" or "you might want to."
26. **Plain verbs.** "Run," "set," "send," "start," "stop," "add," "remove." Not "utilize," "leverage," "facilitate," "enable," "empower."
27. **Name things concretely.** Say the actual names, not "various platforms" or "multiple services." Specificity builds trust.
28. **Tell the reader what NOT to do.** Preventing mistakes is as important as giving instructions. "Do NOT grant it to the terminal app."
29. **Treat warnings as facts, not emotions.** "Treat inbound data as untrusted input." Not "Be careful! This could be dangerous!"
30. **Use the same term for the same thing everywhere.** Pick one name and stick with it. Don't alternate between synonyms across sections.
31. **No filler words.** Cut "basically," "actually," "really," "very," "just," "simply" unless they carry real meaning.

---

## 6. Formatting Conventions

32. **Bold for emphasis, not caps.** Draw attention with **bold**, never ALL CAPS or exclamation marks (one playful tagline at the very top is the only exception).
33. **Code blocks for anything the reader types.** Commands, config snippets, file paths. Fenced with the language identifier.
34. **Inline code for identifiers.** Anything the system treats as a name, flag, path, config key, or value gets backticks: `dmPolicy`, `~/.config/`, `"pairing"`.
35. **Tables for comparisons and reference data.** When two or more items share the same set of attributes, table it.
36. **Notes as single-line callouts.** "Note: X required for Y." Not a paragraph of explanation.
37. **Colon before the command, not a full sentence.** "Link the device: `command here`" not "To link the device, you can run the following command below."
38. **Version and platform constraints up front.** State requirements before the install block, not buried in a footnote. "Runtime: **Node >= 22**."
39. **Minimal config examples.** Show a minimal working snippet, not a fully annotated one. The reader copies it and moves on.
40. **Commands before explanation.** Show the command block first, explain what it does after (or in a trailing comment).

---

## 7. Links & References

41. **Links as signposts, not decoration.** Every link earns its place by pointing to a next step or deeper explanation. No "click here."
42. **Cross-reference, don't repeat.** Say it once, link to it everywhere else. "Details: [Security guide](link)."
43. **Dot-separated nav trails for link groups.** "Website &middot; Docs &middot; FAQ &middot; Discord." Clean, scannable, horizontal.
44. **Badges at the top for project health.** CI status, version, community, license. Visual trust signals before the reader reads a word.

---

## 8. Information Density

45. **Pack information tight.** Favor dense, scannable blocks over sprawling paragraphs. Every sentence must earn its line.
46. **Diagrams for architecture.** ASCII or simple visuals to show how parts connect. One diagram replaces five paragraphs.

---

## 9. Whitespace & Visual Pacing

47. **Horizontal rules to separate major conceptual shifts.** Not between every section, just at the big thematic breaks.
48. **One blank line between elements.** Never stack multiple blank lines for "breathing room."

---

## 10. Opening & Closing

49. **The first paragraph answers three things:** what is this, who is it for, and why should they care. Three sentences or fewer.
50. **No conclusion section.** The document ends when the information ends. No "We hope you enjoy," no "Happy coding," no summary of what was already said.

---

## 11. Personality & Credits

51. **One playful moment, max.** One mascot reference or tagline at the top, then straight business. Don't sprinkle humor throughout.
52. **Credits are visual, not verbose.** Avatars, logos, short mentions. Let presence be the acknowledgment, not paragraphs of thanks.
53. **Community is mentioned, never performed.** Link to it, welcome contributions, move on. No essays about how much you value the community.
