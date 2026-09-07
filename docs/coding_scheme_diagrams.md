Five figures: the shared experimental pipeline, how each of the three
schemes builds its codeword, and the block-circulant decoder whose
radius sets BC's erasure tolerance. Everything here is either a pipeline
the report has to describe anyway, or the structure behind a measured
result. Earlier drafts also carried worked numeric examples and
algorithm flowcharts; those were teaching aids rather than results and
have been dropped.

Figures are drawn from this project's own code (`1D_RS_Galois.py`,
`2D_RS_Galois.py`, `BCcodeEthereum.py`). The BC figures follow the
published construction — Sasidharan, Viterbo & Hoang Dau, *"Block
Circulant Codes with Application to Decentralized Systems,"* IEEE Trans.
Commun. 73(10), 2025 (arXiv:2406.12160) — since that is what the
implementation is meant to realise.

## Experimental pipeline

Every number in the benchmark report comes from running this loop once per
trial. The blob is fixed and the erasure rate is swept; at each rate the
codeword is corrupted at randomly chosen positions and handed to the
decoder. A trial counts as a success only if the bytes that come out the
far end are identical to the ones that went in.

<figure>
<svg viewBox="0 0 300 252" role="img" aria-label="The investigation pipeline used for every scheme, laid out as a three-row serpentine: real application bytes are packed into a blob, encoded and extended, a fraction is withheld to simulate erasure, the decoder attempts recovery, and the result is extracted and unpacked for a byte-for-byte comparison against the original."><defs><marker id="apS" markerWidth="7" markerHeight="7" refX="5.4" refY="2.6" orient="auto"><path d="M0,0 L5.4,2.6 L0,5.2 Z" fill="currentColor"/></marker><marker id="apV" markerWidth="7" markerHeight="7" refX="5.4" refY="2.6" orient="auto"><path d="M0,0 L5.4,2.6 L0,5.2 Z" fill="#15803d"/></marker></defs>
<text x="12" y="12" font-size="8.2" font-weight="700">Same pipeline for every scheme &#8212; only encode/decode changes</text>
<rect x="12" y="26" width="84" height="42" rx="2.5" fill="none" stroke="currentColor" stroke-width="0.8"/>
<text x="54.0" y="39" text-anchor="middle" font-size="6.6" font-weight="700">real application</text>
<text x="54.0" y="50" text-anchor="middle" font-size="6.1" fill="#4a5561">bytes</text>
<text x="54.0" y="60" text-anchor="middle" font-size="6.1" fill="#4a5561">≤126,976 B</text>
<rect x="110" y="26" width="84" height="42" rx="2.5" fill="none" stroke="currentColor" stroke-width="0.8"/>
<text x="152.0" y="39" text-anchor="middle" font-size="6.6" font-weight="700">pack → blob</text>
<text x="152.0" y="50" text-anchor="middle" font-size="6.1" fill="#4a5561">4096 elements</text>
<text x="152.0" y="60" text-anchor="middle" font-size="6.1" fill="#4a5561">EIP-4844</text>
<rect x="208" y="26" width="84" height="42" rx="2.5" fill="none" stroke="currentColor" stroke-width="0.8"/>
<text x="250.0" y="39" text-anchor="middle" font-size="6.6" font-weight="700">encode / extend</text>
<text x="250.0" y="50" text-anchor="middle" font-size="6.1" fill="#4a5561">scheme-specific</text>
<text x="250.0" y="60" text-anchor="middle" font-size="6.1" fill="#4a5561">→ n elements</text>
<rect x="208" y="92" width="84" height="42" rx="2.5" fill="none" stroke="currentColor" stroke-width="0.8"/>
<text x="250.0" y="105" text-anchor="middle" font-size="6.6" font-weight="700">simulate erasure</text>
<text x="250.0" y="116" text-anchor="middle" font-size="6.1" fill="#4a5561">withhold a</text>
<text x="250.0" y="126" text-anchor="middle" font-size="6.1" fill="#4a5561">fraction</text>
<rect x="110" y="92" width="84" height="42" rx="2.5" fill="none" stroke="currentColor" stroke-width="0.8"/>
<text x="152.0" y="105" text-anchor="middle" font-size="6.6" font-weight="700">decode</text>
<text x="152.0" y="116" text-anchor="middle" font-size="6.1" fill="#4a5561">locator +</text>
<text x="152.0" y="126" text-anchor="middle" font-size="6.1" fill="#4a5561">recovery</text>
<rect x="12" y="92" width="84" height="42" rx="2.5" fill="none" stroke="currentColor" stroke-width="0.8"/>
<text x="54.0" y="105" text-anchor="middle" font-size="6.6" font-weight="700">extract</text>
<text x="54.0" y="116" text-anchor="middle" font-size="6.1" fill="#4a5561">restrict back</text>
<text x="54.0" y="126" text-anchor="middle" font-size="6.1" fill="#4a5561">→ 4096</text>
<rect x="12" y="158" width="84" height="42" rx="2.5" fill="none" stroke="currentColor" stroke-width="0.8"/>
<text x="54.0" y="171" text-anchor="middle" font-size="6.6" font-weight="700">unpack → bytes</text>
<text x="54.0" y="182" text-anchor="middle" font-size="6.1" fill="#4a5561">compare to</text>
<text x="54.0" y="192" text-anchor="middle" font-size="6.1" fill="#4a5561">original</text>
<line x1="97.5" y1="47.0" x2="108.5" y2="47.0" stroke="currentColor" stroke-width="0.85" marker-end="url(#apS)"/>
<line x1="195.5" y1="47.0" x2="206.5" y2="47.0" stroke="currentColor" stroke-width="0.85" marker-end="url(#apS)"/>
<line x1="250.0" y1="69.5" x2="250.0" y2="90.5" stroke="currentColor" stroke-width="0.85" marker-end="url(#apS)"/>
<line x1="206.5" y1="113.0" x2="195.5" y2="113.0" stroke="currentColor" stroke-width="0.85" marker-end="url(#apS)"/>
<line x1="108.5" y1="113.0" x2="97.5" y2="113.0" stroke="currentColor" stroke-width="0.85" marker-end="url(#apS)"/>
<line x1="54.0" y1="135.5" x2="54.0" y2="156.5" stroke="currentColor" stroke-width="0.85" marker-end="url(#apS)"/>
<path d="M 97.5 179.0 H 296 V 15 H 54.0 V 24.5" fill="none" stroke="#15803d" stroke-width="0.85" stroke-dasharray="3,2.2" marker-end="url(#apV)"/>
<text x="114" y="190" font-size="6.2" fill="#15803d" font-weight="700">byte-for-byte check</text>
<text x="114" y="200" font-size="5.9" fill="#15803d">blob_matches() &#8212; not the</text>
<text x="114" y="209" font-size="5.9" fill="#15803d">decoder&#8217;s own success flag</text>
<text x="12" y="246" font-size="5.9" fill="#4a5561">1D-RS: one interpolate+NTT pass &#8226; 2D-RS: row-then-column, iterated &#8226; BC: local + pairwise solves</text></svg>
<figcaption>The measurement pipeline. Real application bytes are packed into one EIP-4844 blob (4096 field elements, 31 usable bytes each), the scheme under test expands that blob into a longer codeword, a fraction of the codeword is withheld to stand in for samples peers failed to serve, the decoder tries to rebuild it, and the result is unpacked back to bytes. Only the two shaded-in-meaning stages &#8212; <em>encode/extend</em> and <em>decode</em> &#8212; differ between the three schemes; the input, the erasure model and the test of success are byte-identical for all of them, which is what makes a difference in the results attributable to the code rather than to the setup. The dashed return path is the success test itself: the recovered bytes must equal the original bytes exactly. It deliberately does not ask the decoder whether it succeeded &#8212; one of the three decoders was found reporting success on data it had silently corrupted, and only this comparison caught it.</figcaption>
</figure>

## How each scheme builds its codeword

<figure>
<svg viewBox="0 0 300 300" role="img" aria-label="1D-RS encoding: the k data symbols are the values of a single polynomial sampled at k points; encoding samples that same curve at n equals 2k points, and any k of those samples determine the curve and therefore all the original data."><text x="34" y="26" font-size="9.4" font-weight="700">The blob IS a polynomial, sampled</text>
<text x="34" y="38" font-size="7.4" fill="#4a5561">k data symbols = its values at k points</text>
<polyline points="34.0,133.7 36.8,128.2 39.6,123.0 42.4,118.1 45.2,113.5 48.0,109.1 50.8,104.9 53.6,101.0 56.4,97.3 59.2,93.9 62.0,90.6 64.8,87.6 67.6,84.8 70.4,82.2 73.2,79.8 76.0,77.6 78.8,75.6 81.6,73.8 84.4,72.2 87.2,70.7 90.0,69.4 92.8,68.3 95.6,67.3 98.4,66.5 101.2,65.8 104.0,65.3 106.8,64.9 109.6,64.6 112.4,64.5 115.2,64.5 118.0,64.5 120.8,64.7 123.6,65.0 126.4,65.4 129.2,65.9 132.0,66.5 134.8,67.1 137.6,67.9 140.4,68.7 143.2,69.5 146.0,70.4 148.8,71.4 151.6,72.4 154.4,73.5 157.2,74.6 160.0,75.7 162.8,76.9 165.6,78.0 168.4,79.2 171.2,80.4 174.0,81.6 176.8,82.8 179.6,84.0 182.4,85.1 185.2,86.3 188.0,87.4 190.8,88.5 193.6,89.6 196.4,90.6 199.2,91.6 202.0,92.5 204.8,93.3 207.6,94.1 210.4,94.9 213.2,95.5 216.0,96.1 218.8,96.6 221.6,97.0 224.4,97.3 227.2,97.5 230.0,97.5 232.8,97.5 235.6,97.4 238.4,97.1 241.2,96.7 244.0,96.2 246.8,95.5 249.6,94.7 252.4,93.7 255.2,92.6 258.0,91.3 260.8,89.8 263.6,88.2 266.4,86.4 269.2,84.4 272.0,82.2 274.8,79.8 277.6,77.2 280.4,74.4 283.2,71.4 286.0,68.1" fill="none" stroke="currentColor" stroke-width="1.1" opacity="0.65"/>
<line x1="49.1" y1="107.4" x2="49.1" y2="120" stroke="#1546a0" stroke-width="0.6" opacity="0.45"/>
<circle cx="49.1" cy="107.4" r="3.2" fill="#1546a0"/>
<line x1="104.6" y1="65.2" x2="104.6" y2="120" stroke="#1546a0" stroke-width="0.6" opacity="0.45"/>
<circle cx="104.6" cy="65.2" r="3.2" fill="#1546a0"/>
<line x1="160.0" y1="75.7" x2="160.0" y2="120" stroke="#1546a0" stroke-width="0.6" opacity="0.45"/>
<circle cx="160.0" cy="75.7" r="3.2" fill="#1546a0"/>
<line x1="215.4" y1="96.0" x2="215.4" y2="120" stroke="#1546a0" stroke-width="0.6" opacity="0.45"/>
<circle cx="215.4" cy="96.0" r="3.2" fill="#1546a0"/>
<line x1="270.9" y1="83.1" x2="270.9" y2="120" stroke="#1546a0" stroke-width="0.6" opacity="0.45"/>
<circle cx="270.9" cy="83.1" r="3.2" fill="#1546a0"/>
<line x1="34" y1="120" x2="286" y2="120" stroke="currentColor" stroke-width="0.7"/>
<text x="286" y="131" text-anchor="end" font-size="7.2" fill="#1546a0">k = 4096 data symbols</text>
<defs><marker id="cwA" markerWidth="7" markerHeight="7" refX="5.4" refY="2.6" orient="auto"><path d="M0,0 L5.4,2.6 L0,5.2 Z" fill="#1546a0"/></marker></defs>
<line x1="160.0" y1="138" x2="160.0" y2="160" stroke="#1546a0" stroke-width="1.2" marker-end="url(#cwA)"/>
<text x="168.0" y="150" font-size="7.6" fill="#1546a0">sample the SAME curve at 2k points</text>
<polyline points="34.0,273.7 36.8,268.2 39.6,263.0 42.4,258.1 45.2,253.5 48.0,249.1 50.8,244.9 53.6,241.0 56.4,237.3 59.2,233.9 62.0,230.6 64.8,227.6 67.6,224.8 70.4,222.2 73.2,219.8 76.0,217.6 78.8,215.6 81.6,213.8 84.4,212.2 87.2,210.7 90.0,209.4 92.8,208.3 95.6,207.3 98.4,206.5 101.2,205.8 104.0,205.3 106.8,204.9 109.6,204.6 112.4,204.5 115.2,204.5 118.0,204.5 120.8,204.7 123.6,205.0 126.4,205.4 129.2,205.9 132.0,206.5 134.8,207.1 137.6,207.9 140.4,208.7 143.2,209.5 146.0,210.4 148.8,211.4 151.6,212.4 154.4,213.5 157.2,214.6 160.0,215.7 162.8,216.9 165.6,218.0 168.4,219.2 171.2,220.4 174.0,221.6 176.8,222.8 179.6,224.0 182.4,225.1 185.2,226.3 188.0,227.4 190.8,228.5 193.6,229.6 196.4,230.6 199.2,231.6 202.0,232.5 204.8,233.3 207.6,234.1 210.4,234.9 213.2,235.5 216.0,236.1 218.8,236.6 221.6,237.0 224.4,237.3 227.2,237.5 230.0,237.5 232.8,237.5 235.6,237.4 238.4,237.1 241.2,236.7 244.0,236.2 246.8,235.5 249.6,234.7 252.4,233.7 255.2,232.6 258.0,231.3 260.8,229.8 263.6,228.2 266.4,226.4 269.2,224.4 272.0,222.2 274.8,219.8 277.6,217.2 280.4,214.4 283.2,211.4 286.0,208.1" fill="none" stroke="currentColor" stroke-width="1.1" opacity="0.65"/>
<line x1="49.1" y1="247.4" x2="49.1" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="49.1" cy="247.4" r="3.2" fill="#1546a0"/>
<line x1="76.8" y1="217.0" x2="76.8" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="76.8" cy="217.0" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<line x1="104.6" y1="205.2" x2="104.6" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="104.6" cy="205.2" r="3.2" fill="#1546a0"/>
<line x1="132.3" y1="206.5" x2="132.3" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="132.3" cy="206.5" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<line x1="160.0" y1="215.7" x2="160.0" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="160.0" cy="215.7" r="3.2" fill="#1546a0"/>
<line x1="187.7" y1="227.3" x2="187.7" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="187.7" cy="227.3" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<line x1="215.4" y1="236.0" x2="215.4" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="215.4" cy="236.0" r="3.2" fill="#1546a0"/>
<line x1="243.2" y1="236.4" x2="243.2" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="243.2" cy="236.4" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<line x1="270.9" y1="223.1" x2="270.9" y2="260" stroke="currentColor" stroke-width="0.5" opacity="0.3"/>
<circle cx="270.9" cy="223.1" r="3.2" fill="#1546a0"/>
<line x1="34" y1="260" x2="286" y2="260" stroke="currentColor" stroke-width="0.7"/>
<text x="286" y="271" text-anchor="end" font-size="7.2">n = 8192 codeword symbols</text>
<circle cx="38" cy="268" r="3" fill="#1546a0"/>
<text x="45" y="271" font-size="6.8" fill="#1546a0">original</text>
<circle cx="86" cy="268" r="3" fill="#fff" stroke="#c62828" stroke-width="1.3"/>
<text x="93" y="271" font-size="6.8" fill="#c62828">new</text>
<text x="34" y="286" font-size="7.6" font-weight="700">Any k of the n samples pin down the curve &#8212;</text>
<text x="34" y="296" font-size="7.6" font-weight="700">so any k recover every original symbol.</text></svg>
<figcaption>1D-RS. The blob&#8217;s k field elements are not raw bytes to be copied; they are the <em>values of a single polynomial</em> sampled at k points. Encoding finds that polynomial and samples it at n = 2k points instead. Because a degree-&lt;k polynomial is pinned down by any k of its values, any k surviving symbols reconstruct the curve and hence every original symbol. 2&#215; overhead.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 300 300" role="img" aria-label="2D-RS encoding: the blob is reshaped into a k by k grid, each row is extended to twice its length and then each column is extended likewise, giving an n by n grid at four times overhead in which every row and every column is independently a 1D-RS codeword."><defs><pattern id="hR" width="4" height="4" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="4" stroke="currentColor" stroke-width="0.8" opacity="0.5"/></pattern></defs>
<text x="26" y="26" font-size="9.4" font-weight="700">The same trick, twice</text>
<text x="26" y="38" font-size="7.4" fill="#4a5561">once along every row, then once down every column</text>
<rect x="60" y="62" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="77" y="62" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="94" y="62" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="111" y="62" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="128" y="62" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="145" y="62" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="162" y="62" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="179" y="62" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="60" y="79" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="77" y="79" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="94" y="79" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="111" y="79" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="128" y="79" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="145" y="79" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="162" y="79" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="179" y="79" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="60" y="96" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="77" y="96" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="94" y="96" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="111" y="96" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="128" y="96" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="145" y="96" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="162" y="96" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="179" y="96" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="60" y="113" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="77" y="113" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="94" y="113" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="111" y="113" width="17" height="17" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="128" y="113" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="145" y="113" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="162" y="113" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="179" y="113" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="60" y="130" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="77" y="130" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="94" y="130" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="111" y="130" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="128" y="130" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="145" y="130" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="162" y="130" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="179" y="130" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="60" y="147" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="77" y="147" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="94" y="147" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="111" y="147" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="128" y="147" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="145" y="147" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="162" y="147" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="179" y="147" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="60" y="164" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="77" y="164" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="94" y="164" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="111" y="164" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="128" y="164" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="145" y="164" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="162" y="164" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="179" y="164" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="60" y="181" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="77" y="181" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="94" y="181" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="111" y="181" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="128" y="181" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="145" y="181" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="162" y="181" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="179" y="181" width="17" height="17" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<line x1="128" y1="62" x2="128" y2="198" stroke="currentColor" stroke-width="1.3"/>
<line x1="60" y1="130" x2="196" y2="130" stroke="currentColor" stroke-width="1.3"/>
<defs><marker id="cwB" markerWidth="7" markerHeight="7" refX="5.4" refY="2.6" orient="auto"><path d="M0,0 L5.4,2.6 L0,5.2 Z" fill="#1546a0"/></marker></defs>
<line x1="125" y1="96.0" x2="193" y2="96.0" stroke="#1546a0" stroke-width="1.2" marker-end="url(#cwB)"/>
<text x="202" y="98.5" font-size="7.2" fill="#1546a0">extend</text>
<text x="202" y="107.0" font-size="7.2" fill="#1546a0">each row</text>
<line x1="94.0" y1="127" x2="94.0" y2="195" stroke="#1546a0" stroke-width="1.2" marker-end="url(#cwB)"/>
<text x="90.0" y="211" text-anchor="middle" font-size="7.2" fill="#1546a0">extend each column</text>
<text x="60" y="56" font-size="7.0" fill="#1546a0" font-weight="700">k&#215;k data</text>
<rect x="26" y="223" width="10" height="9" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<text x="40" y="230" font-size="7.0">original blob</text>
<rect x="120" y="223" width="10" height="9" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<text x="134" y="230" font-size="7.0">parity (4&#215; overhead)</text>
<text x="26" y="274" font-size="7.6" font-weight="700">Every row and every column is now its own</text>
<text x="26" y="284" font-size="7.6" font-weight="700">1D-RS codeword, so a lost cell can be repaired</text>
<text x="26" y="294" font-size="7.6" font-weight="700">from its row or its column &#8212; whichever survives.</text></svg>
<figcaption>2D-RS. The blob is reshaped into a k&#215;k grid and the 1D-RS step is applied twice: once to extend every row, then once to extend every column of the result. The outcome is an n&#215;n grid at 4&#215; overhead in which every row and every column is independently a 1D-RS codeword &#8212; so a lost cell can be repaired from whichever of its two lines has enough survivors, which is what lets the iterative decoder cascade.</figcaption>
</figure>

## Block-circulant structure

<figure>
<svg viewBox="0 0 620 620" role="img" aria-label="Block-circulant topology for mu=4, omega=2, rho=2, lambda=2: eight information symbols and eight parity symbols alternate around a ring; each local code spans three consecutive groups, so adjacent local codes overlap by one information group">
<defs><marker id="arrRing" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="currentColor"/></marker></defs>
<circle cx="310.0" cy="300.0" r="195" fill="none" stroke="currentColor" stroke-width="0.6" opacity="0.25" stroke-dasharray="3,4"/>
<path d="M 211.7 62.6 A 257 257 0 0 1 547.4 398.3" fill="none" stroke="#1d4ed8" stroke-width="2.4"/>
<text x="426.7" y="18.2" text-anchor="middle" font-size="11.5" fill="#1d4ed8" font-weight="700">local code 1</text>
<text x="426.7" y="34.2" text-anchor="middle" font-size="9.3" fill="#1d4ed8">[n&#8320;=6, k&#8320;=4, d&#8320;=3]</text>
<rect x="262.0" y="82.0" width="96" height="46" rx="5" fill="#dbeafe" stroke="#1d4ed8" stroke-width="1.3"/>
<text x="310.0" y="101.0" text-anchor="middle" font-size="13">d&#8321;</text>
<text x="310.0" y="121.0" text-anchor="middle" font-size="13">d&#8322;</text>
<rect x="399.9" y="139.1" width="96" height="46" rx="5" fill="#fed7aa" stroke="#c2410c" stroke-width="1.3"/>
<text x="447.9" y="158.1" text-anchor="middle" font-size="13">p&#8321;&#8321;</text>
<text x="447.9" y="178.1" text-anchor="middle" font-size="13">p&#8321;&#8322;</text>
<rect x="457.0" y="277.0" width="96" height="46" rx="5" fill="#dbeafe" stroke="#1d4ed8" stroke-width="1.3"/>
<text x="505.0" y="296.0" text-anchor="middle" font-size="13">d&#8323;</text>
<text x="505.0" y="316.0" text-anchor="middle" font-size="13">d&#8324;</text>
<rect x="399.9" y="414.9" width="96" height="46" rx="5" fill="#fed7aa" stroke="#c2410c" stroke-width="1.3"/>
<text x="447.9" y="433.9" text-anchor="middle" font-size="13">p&#8322;&#8321;</text>
<text x="447.9" y="453.9" text-anchor="middle" font-size="13">p&#8322;&#8322;</text>
<rect x="262.0" y="472.0" width="96" height="46" rx="5" fill="#dbeafe" stroke="#1d4ed8" stroke-width="1.3"/>
<text x="310.0" y="491.0" text-anchor="middle" font-size="13">d&#8325;</text>
<text x="310.0" y="511.0" text-anchor="middle" font-size="13">d&#8326;</text>
<rect x="124.1" y="414.9" width="96" height="46" rx="5" fill="#fed7aa" stroke="#c2410c" stroke-width="1.3"/>
<text x="172.1" y="433.9" text-anchor="middle" font-size="13">p&#8323;&#8321;</text>
<text x="172.1" y="453.9" text-anchor="middle" font-size="13">p&#8323;&#8322;</text>
<rect x="67.0" y="277.0" width="96" height="46" rx="5" fill="#dbeafe" stroke="#1d4ed8" stroke-width="1.3"/>
<text x="115.0" y="296.0" text-anchor="middle" font-size="13">d&#8327;</text>
<text x="115.0" y="316.0" text-anchor="middle" font-size="13">d&#8328;</text>
<rect x="124.1" y="139.1" width="96" height="46" rx="5" fill="#fed7aa" stroke="#c2410c" stroke-width="1.3"/>
<text x="172.1" y="158.1" text-anchor="middle" font-size="13">p&#8324;&#8321;</text>
<text x="172.1" y="178.1" text-anchor="middle" font-size="13">p&#8324;&#8322;</text>
<rect x="30" y="560" width="16" height="16" rx="3" fill="#dbeafe" stroke="#1d4ed8" stroke-width="1.2"/>
<text x="52" y="573" font-size="10.5">information symbols (&omega;=2 per group, &mu;&omega;=8 total = k)</text>
<rect x="30" y="582" width="16" height="16" rx="3" fill="#fed7aa" stroke="#c2410c" stroke-width="1.2"/>
<text x="52" y="595" font-size="10.5">parity symbols (&rho;=2 per group, &mu;&rho;=8 total = n-k)</text>
</svg>
<figcaption>Block-circulant layout (drawn at &#956;=4 for legibility; the benchmark runs &#956;=2048). Information blocks alternate with parity blocks around a ring, and each local code covers its own parity plus the information of &#955; consecutive blocks. 2&#215; overhead, the same as 1D-RS, but the parity is local rather than global.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 300 300" role="img" aria-label="Block-circulant decoding is local: a block holding at most rho erasures is solved by its own parity equations, a block holding more is stuck, and an adjacent pair holding at most two rho between them can sometimes be solved jointly. The guaranteed correction is only d minus 1, four erasures across the entire codeword; beyond that recovery depends on erasures remaining thinly spread across the local blocks."><text x="30" y="24" font-size="9.4" font-weight="700">BC repairs locally, so spread matters</text>
<text x="30" y="36" font-size="7.4" fill="#4a5561">each local code covers &#961;=2 parity + &#955;&#969;=4 information symbols</text>
<rect x="30" y="58" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="51" y="58" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="72" y="58" width="21" height="17" fill="#1b7a34" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="82.5" y="69.5" text-anchor="middle" font-size="7.6" fill="#1b7a34" font-weight="700">?</text>
<rect x="93" y="58" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="114" y="58" width="21" height="17" fill="#1b7a34" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="124.5" y="69.5" text-anchor="middle" font-size="7.6" fill="#1b7a34" font-weight="700">?</text>
<rect x="135" y="58" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<text x="164" y="69.5" font-size="7.2" fill="#1b7a34" font-weight="700">&#8804; &#961;: solved</text>
<text x="30" y="86" font-size="6.8" fill="#4a5561">Phase 1 &#8212; two unknowns, two parity equations.</text>
<rect x="30" y="106" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="51" y="106" width="21" height="17" fill="#c62828" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="61.5" y="117.5" text-anchor="middle" font-size="7.6" fill="#c62828" font-weight="700">?</text>
<rect x="72" y="106" width="21" height="17" fill="#c62828" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="82.5" y="117.5" text-anchor="middle" font-size="7.6" fill="#c62828" font-weight="700">?</text>
<rect x="93" y="106" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="114" y="106" width="21" height="17" fill="#c62828" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="124.5" y="117.5" text-anchor="middle" font-size="7.6" fill="#c62828" font-weight="700">?</text>
<rect x="135" y="106" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<text x="164" y="117.5" font-size="7.2" fill="#c62828" font-weight="700">&gt; &#961;: stuck</text>
<text x="30" y="134" font-size="6.8" fill="#4a5561">Three unknowns, still only two equations.</text>
<rect x="30" y="154" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="51" y="154" width="21" height="17" fill="#1546a0" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="61.5" y="165.5" text-anchor="middle" font-size="7.6" fill="#1546a0" font-weight="700">?</text>
<rect x="72" y="154" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="93" y="154" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="114" y="154" width="21" height="17" fill="#1546a0" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="124.5" y="165.5" text-anchor="middle" font-size="7.6" fill="#1546a0" font-weight="700">?</text>
<rect x="135" y="154" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<text x="164" y="165.5" font-size="7.2" fill="#1546a0" font-weight="700"></text>
<text x="164" y="173" font-size="7.2" fill="#1546a0" font-weight="700">pair: &#8804; 2&#961;</text>
<rect x="30" y="174" width="21" height="17" fill="#1546a0" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="40.5" y="185.5" text-anchor="middle" font-size="7.6" fill="#1546a0" font-weight="700">?</text>
<rect x="51" y="174" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="72" y="174" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="93" y="174" width="21" height="17" fill="#1546a0" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="103.5" y="185.5" text-anchor="middle" font-size="7.6" fill="#1546a0" font-weight="700">?</text>
<rect x="114" y="174" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<rect x="135" y="174" width="21" height="17" fill="none" stroke="currentColor" stroke-width="0.6"/>
<text x="164" y="185.5" font-size="7.2" fill="#1546a0" font-weight="700"></text>
<path d="M 23 152 v 41" stroke="#1546a0" stroke-width="1.1"/>
<text x="30" y="206" font-size="6.8" fill="#4a5561">Phase 2 &#8212; two adjacent blocks solved together,</text>
<text x="30" y="215" font-size="6.8" fill="#4a5561">when their stacked equations determine them.</text>
<rect x="24" y="232" width="178" height="54" fill="none" stroke="#1546a0" stroke-width="0.9"/>
<text x="30" y="246" font-size="7.4" font-weight="700" fill="#1546a0">Guaranteed: only d&#8722;1 = 4 erasures</text>
<text x="30" y="257" font-size="7.0" fill="#1b1f24">across the whole 8192-symbol codeword.</text>
<text x="30" y="269" font-size="7.0" fill="#1b1f24">Beyond that it works only while erasures stay</text>
<text x="30" y="278" font-size="7.0" fill="#1b1f24">thinly spread across the &#956;=2048 blocks.</text></svg>
<figcaption>Why BC&#8217;s tolerance is limited. Repair is local: a block holding at most &#961; erasures is solved by its own two parity equations; one holding more is stuck; an adjacent pair holding at most 2&#961; between them can sometimes be solved jointly. The guaranteed correction is only d&#8722;1 = 4 erasures across the entire 8192-symbol codeword, so beyond that BC depends on erasures staying thinly spread across the &#956;=2048 local blocks &#8212; which random erasure stops providing well below the rates the Reed-Solomon variants reach.</figcaption>
</figure>
