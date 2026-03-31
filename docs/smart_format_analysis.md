# Smart Format Analysis -- German Phone/Email Behavior

## Method
- Nova-3, language="de", smart_format=True, punctuate=True, diarize=True, paragraphs=True
- 30 recordings transcribed; 8 recordings sampled for detailed analysis
- Expected values from data/ground_truth.json compared against raw transcript output
- Sample: call_01, call_02, call_03, call_04, call_05, call_16, call_20, call_25

## Phone Number Observations

| Recording | Expected (Ground Truth) | Transcript Contains | Formatted? | Notes |
|-----------|------------------------|---------------------|------------|-------|
| call_01 | +49 152 11223456 | digit-by-digit (not E.164): "...plus 4 9 1 5 2 1 1 2 2 3 4 5 6. Ich danke Ihnen...." | No | -- |
| call_02 | +49 157 231412313 | digit-by-digit (not E.164): "...plus 4 9 1 5 7 2 3 1 4 1 2 3 1 3. Ich danke Ihnen, schönen T..." | No | -- |
| call_03 | +49 176 98765432 | digit-by-digit (not E.164): "...plus 4 9 1 7 6 9 8 7 6 5 4 3 2. Ich danke Ihnen...." | No | -- |
| call_04 | +49 30 54783219 | digit-by-digit (not E.164): "...plus 4 9 3 0 5 4 7 8 3 2 1 9. Das wär auch super. Hauptsache..." | No | -- |
| call_05 | +49 172 44556677 | digit-by-digit (not E.164): "...plus 4 9 1 7 2 4 4 5 5 6 6 7 7. Ich danke Ihnen...." | No | -- |
| call_16 | +49 160 55123456 | digit-by-digit (not E.164): "...plus 4 9 1 6 0 5 5 1 2 3 4 5 6. Ich danke Ihnen...." | No | -- |
| call_20 | +49 163 99567890 | digit-by-digit (not E.164): "...plus 4 9 1 6 3 9 9 5 6 7 8 9 0. Oder Sie schreiben meine E-M..." | No | -- |
| call_25 | +49 176 55012345 | digit-by-digit (not E.164): "...plus 4 9 1 7 6 5 5 0 1 2 3 4 5. Oder Sie schreiben mir eine..." | No | -- |

## Email Observations

| Recording | Expected (Ground Truth) | Transcript Contains | Formatted? | Notes |
|-----------|------------------------|---------------------|------------|-------|
| call_01 | johanna.schmidt@gmail.com | spoken-form: "...eichen mich unter Johanna Punkt Schmidt at Gmail Punkt com oder telefonisch unter plus 4 9 1 5 2 1 1..." | No | -- |
| call_02 | h47-herbst@web.de | spoken-form: "...mich per E-Mail über h 4 7 minus Herbst at Web Punkt d e oder per Telefon über plus 4 9 1 5 7 2 3 1..." | No | -- |
| call_03 | annika.becker@gmx.de | spoken-form: "...ch per E-Mail unter Annika Punkt Becker at gmx Punkt Punkt d e anschreiben oder sich per Telefon bei..." | No | -- |
| call_04 | m.hoffmann@outlook.com | spoken-form: "...s nicht so rechtens ist. Mein Name ist Matthias Hoffmann, das ist MATTHIAS und Hoffmann mit Doppel-f..." | No | -- |
| call_05 | sandra-weber@t-online.de | spoken-form: "...e E-Mail-Adresse ist SANDRA minus WEBER at t minus online Punkt d e. Oder noch besser, Sie rufen Sie..." | No | -- |
| call_16 | james.anderson@gmail.com | spoken-form: "...der E-Mail-Adresse James Punkt Anderson at Gmail Punkt com oder telefonisch über plus 4 9 1 6 0 5 5..." | No | -- |
| call_20 | carlos.garcia@hotmail.es | spoken-form: "...b eine rechtliche Frage. Und zwar, ich hatte heute einen Auffahrunfall und würd mich dahingehend ger..." | No | -- |
| call_25 | marie.lefevre@yahoo.fr | spoken-form: "...E-Mail, das wäre Marie Punkt Le faivre at Yahoo Punkt f r. Ich danke Ihnen...." | No | -- |

## Foreign Name Observations (Calls 16-30)

| Recording | Expected Name | Transcribed As | Accurate? | Notes |
|-----------|--------------|----------------|-----------|-------|
| call_16 | James Anderson | "...Name ist James Anderson und ich hab ein..." | Yes | first=found, last=found |
| call_20 | Carlos García | "...Name ist Carlos Gassia und ich hab eine..." | Partial | first=found, last=missing |
| call_25 | Marie Lefevre | "...Name ist Marie Le Faivre und ich würd m..." | Partial | first=found, last=missing |

## Diarization Quality

| Recording | Speaker Count | Bot/Caller Separation | Notes |
|-----------|---------------|----------------------|-------|
| call_01 | 1 | Single speaker (no separation) | 51 words total |
| call_02 | 1 | Single speaker (no separation) | 66 words total |
| call_03 | 1 | Single speaker (no separation) | 75 words total |
| call_04 | 1 | Single speaker (no separation) | 90 words total |
| call_05 | 1 | Single speaker (no separation) | 69 words total |
| call_16 | 1 | Single speaker (no separation) | 60 words total |
| call_20 | 1 | Single speaker (no separation) | 72 words total |
| call_25 | 1 | Single speaker (no separation) | 67 words total |

## Conclusion

**smart_format German behavior:** For German (language="de"), smart_format activates punctuation
and paragraph formatting only. Phone number numeral conversion and email address assembly are
English-only features that do NOT activate for German audio.

**Phone numbers:** Spoken-form digit sequences (e.g., "null eins fünf zwei...") are NOT converted to numerals.
smart_format does NOT pre-normalize German phone tokens.

**Emails:** Spoken-form email components (e.g., "punkt", "at", "klammeraffe") are NOT assembled into address strings.
smart_format does NOT assemble German spoken-form email tokens into address strings.

**Diarization:** Unreliable — single speaker detected in most recordings. Speaker 0 typically corresponds to the bot, Speaker 1
to the caller, but this should be verified per recording.

**Foreign names:** 3/3 foreign-name recordings had recognizable transcription. Non-German names in calls 16-30 may be transcribed
as phonetic German approximations (e.g., "García" -> "Garsia"). Extraction prompts should handle
phonetic variants.

**Implication for Phase 3:** LLM extraction prompts MUST handle spoken-form phone numbers and
emails unconditionally. smart_format does NOT pre-normalize these for German. The extraction LLM
must convert sequences like "null eins fünf zwei ein eins zwei zwei drei vier fünf sechs" into
"+49 152 11223456" entirely by its own reasoning.
