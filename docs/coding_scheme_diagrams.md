Five figures: the shared experimental pipeline, how each scheme builds its
codeword, and the two block-circulant figures that explain why an optimal
code can still decode poorly. Everything here is either a pipeline the
report has to describe anyway, or the structure behind a measured result.
Earlier drafts also carried worked numeric examples and algorithm
flowcharts; those were teaching aids rather than results and have been
dropped.

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
scheme's own decoder.

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
<figcaption>The measurement pipeline. Real application bytes are packed into one EIP-4844 blob (4096 field elements, 31 usable bytes each), the scheme under test expands that blob into a longer codeword, a fraction of the codeword is withheld to stand in for samples peers failed to serve, the decoder tries to rebuild it, and the result is unpacked back to bytes. Only <em>encode/extend</em> and <em>decode</em> differ between schemes; the input, the erasure model and the test of success are byte-identical for all of them, which is what makes a difference in the results attributable to the code rather than to the setup. The dashed return path is the success test itself: the recovered bytes must equal the original bytes exactly. It deliberately does not ask the decoder whether it succeeded &#8212; one decoder was found reporting success on data it had silently corrupted, and only this comparison caught it.</figcaption>
</figure>


## How each scheme builds its codeword

The two Reed-Solomon variants share one idea applied at different
dimensions. Both figures lead with that idea rather than with the
transform steps, because the mechanism is easier to follow once the
purpose is clear.

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
<figcaption>1D-RS. The blob&#8217;s k field elements are not raw bytes to be copied; they are the <em>values of a single polynomial</em> sampled at k points. Encoding finds that polynomial and samples it at n = 2k points instead. Because a degree-&lt;k polynomial is pinned down by any k of its values, any k surviving symbols reconstruct the curve and hence every original symbol. 2&#215; overhead, and the reason 1D-RS reaches its theoretical limit exactly.</figcaption>
</figure>


<figure>
<svg viewBox="0 0 300 300" role="img" aria-label="2D-RS encoding: the blob is reshaped into a 64 by 64 grid, each row is extended from 64 to 96 cells and then each column is extended from 64 to 88, giving an 88 by 96 grid at 2.06 times overhead in which every row and every column is independently a 1D-RS codeword."><defs><pattern id="hR" width="4" height="4" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="4" stroke="currentColor" stroke-width="0.8" opacity="0.5"/></pattern></defs>
<text x="26" y="26" font-size="9.4" font-weight="700">The same trick, twice</text>
<text x="26" y="38" font-size="7.4" fill="#4a5561">rows 64→96, columns 64→88: overall rate 0.485</text>
<rect x="62" y="62" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="62" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="62" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="62" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="62" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="62" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="62" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="62" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="62" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="62" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="62" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="74" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="74" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="74" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="74" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="74" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="74" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="74" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="74" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="74" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="74" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="74" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="86" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="86" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="86" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="86" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="86" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="86" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="86" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="86" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="86" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="86" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="86" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="98" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="98" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="98" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="98" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="98" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="98" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="98" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="98" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="98" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="98" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="98" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="110" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="110" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="110" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="110" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="110" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="110" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="110" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="110" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="110" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="110" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="110" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="122" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="122" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="122" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="122" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="122" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="122" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="122" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="122" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="122" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="122" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="122" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="134" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="134" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="134" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="134" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="134" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="134" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="134" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="134" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="134" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="134" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="134" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="146" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="146" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="146" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="146" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="146" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="146" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="146" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="146" width="12" height="12" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="146" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="146" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="146" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="158" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="170" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="62" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="74" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="86" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="98" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="110" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="122" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="134" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="146" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="158" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="170" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<rect x="182" y="182" width="12" height="12" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<line x1="158" y1="62" x2="158" y2="194" stroke="currentColor" stroke-width="1.3"/>
<line x1="62" y1="158" x2="194" y2="158" stroke="currentColor" stroke-width="1.3"/>
<defs><marker id="cwB" markerWidth="7" markerHeight="7" refX="5.4" refY="2.6" orient="auto"><path d="M0,0 L5.4,2.6 L0,5.2 Z" fill="#1546a0"/></marker></defs>
<line x1="155" y1="110.0" x2="191" y2="110.0" stroke="#1546a0" stroke-width="1.2" marker-end="url(#cwB)"/>
<text x="200" y="112.5" font-size="7.2" fill="#1546a0">extend</text>
<text x="200" y="121.0" font-size="7.2" fill="#1546a0">each row</text>
<line x1="110.0" y1="155" x2="110.0" y2="191" stroke="#1546a0" stroke-width="1.2" marker-end="url(#cwB)"/>
<text x="106.0" y="207" text-anchor="middle" font-size="7.2" fill="#1546a0">extend each column</text>
<text x="62" y="56" font-size="7.0" fill="#1546a0" font-weight="700">64&#215;64 data</text>
<rect x="26" y="213" width="10" height="9" fill="#1546a0" opacity="0.72" stroke="currentColor" stroke-width="0.55"/>
<text x="40" y="220" font-size="7.0">original blob</text>
<rect x="120" y="213" width="10" height="9" fill="url(#hR)" stroke="currentColor" stroke-width="0.55"/>
<text x="134" y="220" font-size="7.0">parity (2.06&#215; overhead)</text>
<text x="26" y="238" font-size="7.6" font-weight="700">Every row and every column is now its own</text>
<text x="26" y="248" font-size="7.6" font-weight="700">1D-RS codeword, so a lost cell can be repaired</text>
<text x="26" y="258" font-size="7.6" font-weight="700">from its row or its column &#8212; whichever survives.</text></svg>
<figcaption>2D-RS. The blob is reshaped into a 64&#215;64 grid and the 1D-RS step is applied twice: once to extend every row, then once to extend every column of the result. Every row and every column of the outcome is independently a 1D-RS codeword, so a lost cell can be repaired from whichever of its two lines has enough survivors, which is what lets the iterative decoder cascade. The grid drawn here is schematic. The real extension is 64&#8594;96 along rows and 64&#8594;88 down columns, rather than the 64&#8594;128 of earlier drafts: a product code&#8217;s rate is the <em>product</em> of its component rates, so doubling both axes costs 4&#215; storage and made the comparison against 2&#215;-overhead schemes unfair. Component rates 64/96 and 64/88 give 0.485 overall at 2.06&#215; storage &#8212; the closest to rate 0.5 reachable in this field, since the length-90 NTT an even 90&#215;90 split would need does not exist here.</figcaption>
</figure>


## Block-circulant structure

Block-circulant codes replace one global polynomial with many small local
ones. How much they overlap is the parameter that decides whether the
resulting code is any good.

<figure>
<svg viewBox="0 0 300 300" role="img" aria-label="Block-circulant overlap. With lambda equal to two, a parity block is computed from only two information blocks and the minimum distance is two rho plus one. With lambda equal to mu, every parity block is computed from every information block and the minimum distance rises to 4097, which equals n minus k plus one, the Singleton bound, making the code MDS."><defs><marker id="bcar" markerWidth="6" markerHeight="6" refX="4.6" refY="2.2" orient="auto"><path d="M0,0 L4.6,2.2 L0,4.4 Z" fill="context-stroke"/></marker></defs>
<text x="30" y="24" font-size="9.4" font-weight="700">Full overlap makes the code optimal</text>
<text x="30" y="36" font-size="7.4" fill="#4a5561">how many information blocks each parity block sees</text>
<text x="30" y="60" font-size="7.8" font-weight="700" fill="#c62828">&#955; = 2  (three of the five rows swept)</text>
<rect x="30" y="68" width="46" height="18" fill="#1546a0" opacity="0.16" stroke="currentColor" stroke-width="0.6"/>
<text x="53.0" y="80" text-anchor="middle" font-size="7.0">m<tspan font-size="5.4" dy="1.5">0</tspan></text>
<rect x="86" y="68" width="46" height="18" fill="#1546a0" opacity="0.16" stroke="currentColor" stroke-width="0.6"/>
<text x="109.0" y="80" text-anchor="middle" font-size="7.0">m<tspan font-size="5.4" dy="1.5">1</tspan></text>
<rect x="142" y="68" width="46" height="18" fill="#1546a0" opacity="0.16" stroke="currentColor" stroke-width="0.6"/>
<text x="165.0" y="80" text-anchor="middle" font-size="7.0">m<tspan font-size="5.4" dy="1.5">2</tspan></text>
<rect x="198" y="68" width="46" height="18" fill="#1546a0" opacity="0.16" stroke="currentColor" stroke-width="0.6"/>
<text x="221.0" y="80" text-anchor="middle" font-size="7.0">m<tspan font-size="5.4" dy="1.5">3</tspan></text>
<rect x="114.0" y="122" width="46" height="18" fill="#c62828" opacity="0.20" stroke="#c62828" stroke-width="0.9"/>
<text x="137.0" y="134" text-anchor="middle" font-size="7.0" font-weight="700" fill="#c62828">p<tspan font-size="5.4" dy="1.5">0</tspan></text>
<path d="M 53.0 87 L 137.0 121" stroke="#c62828" stroke-width="0.9" opacity="0.75" marker-end="url(#bcar)"/>
<path d="M 109.0 87 L 137.0 121" stroke="#c62828" stroke-width="0.9" opacity="0.75" marker-end="url(#bcar)"/>
<text x="30" y="154" font-size="6.8" fill="#4a5561">Parity block 0 is computed from 2 of the &#956; blocks.</text>
<text x="30" y="172" font-size="7.8" font-weight="700" fill="#1b7a34">&#955; = &#956;  (&#969;2048 &#955;2 and &#969;1024 &#955;4)</text>
<rect x="30" y="180" width="46" height="18" fill="#1546a0" opacity="0.16" stroke="currentColor" stroke-width="0.6"/>
<text x="53.0" y="192" text-anchor="middle" font-size="7.0">m<tspan font-size="5.4" dy="1.5">0</tspan></text>
<rect x="86" y="180" width="46" height="18" fill="#1546a0" opacity="0.16" stroke="currentColor" stroke-width="0.6"/>
<text x="109.0" y="192" text-anchor="middle" font-size="7.0">m<tspan font-size="5.4" dy="1.5">1</tspan></text>
<rect x="142" y="180" width="46" height="18" fill="#1546a0" opacity="0.16" stroke="currentColor" stroke-width="0.6"/>
<text x="165.0" y="192" text-anchor="middle" font-size="7.0">m<tspan font-size="5.4" dy="1.5">2</tspan></text>
<rect x="198" y="180" width="46" height="18" fill="#1546a0" opacity="0.16" stroke="currentColor" stroke-width="0.6"/>
<text x="221.0" y="192" text-anchor="middle" font-size="7.0">m<tspan font-size="5.4" dy="1.5">3</tspan></text>
<rect x="114.0" y="234" width="46" height="18" fill="#1b7a34" opacity="0.20" stroke="#1b7a34" stroke-width="0.9"/>
<text x="137.0" y="246" text-anchor="middle" font-size="7.0" font-weight="700" fill="#1b7a34">p<tspan font-size="5.4" dy="1.5">0</tspan></text>
<path d="M 53.0 199 L 137.0 233" stroke="#1b7a34" stroke-width="0.9" opacity="0.75" marker-end="url(#bcar)"/>
<path d="M 109.0 199 L 137.0 233" stroke="#1b7a34" stroke-width="0.9" opacity="0.75" marker-end="url(#bcar)"/>
<path d="M 165.0 199 L 137.0 233" stroke="#1b7a34" stroke-width="0.9" opacity="0.75" marker-end="url(#bcar)"/>
<path d="M 221.0 199 L 137.0 233" stroke="#1b7a34" stroke-width="0.9" opacity="0.75" marker-end="url(#bcar)"/>
<text x="30" y="266" font-size="6.8" fill="#4a5561">Parity block 0 is computed from every block.</text>
<rect x="24" y="270" width="252" height="22" fill="none" stroke="#1546a0" stroke-width="0.9"/>
<text x="30" y="284" font-size="7.2" fill="#1b1f24"><tspan font-weight="700">d = &#955;&#961; + 1</tspan>, up to 4097 = n &#8722; k + 1 (Singleton) at &#955; = &#956;.</text></svg>
<figcaption>Overlap decides the code&#8217;s guarantee. Minimum distance is <em>d</em> = &#955;&#961; + 1, so the more information blocks each parity block depends on, the more erasures the code is <em>guaranteed</em> to survive. At &#955; = &#956; every parity block depends on every information block and <em>d</em> reaches 4097 = <em>n</em> &#8722; <em>k</em> + 1, the Singleton bound: as a code that is MDS, exactly as good as Reed-Solomon. Two of the five rows swept are like that &#8212; &#969;2048 &#955;2, where &#956; = 2, and &#969;1024 &#955;4. The &#955;=2 rows at &#956; = 4 and 8 and the &#955;=3 row are not, with worst-case guarantees of 0.250, 0.125 and 0.375. (The project&#8217;s first parameterisation, &#969; = &#961; = 2 with &#956; = 2048, had <em>d</em> = 5: guaranteed to correct only four erasures in an 8192-symbol codeword.)</figcaption>
</figure>


## Why block-circulant tolerance is limited

Whatever the code guarantees, the decoder stops early, and for the same
reason in every row: it never looks beyond a single local block. Even the
two MDS rows — where any 4096 surviving symbols determine the blob, exactly
as for 1D-RS — stop recovering near a third and a fifth of the codeword
respectively.

<figure>
<svg viewBox="0 0 300 324" role="img" aria-label="Why block-circulant tolerance is limited by its decoder. One local block\u2019s support is its own rho parity symbols plus the lambda times omega message symbols it covers, and the block solves only while its support holds at most rho erasures. That holds while lambda omega x plus rho x is at most rho, so with rho equal to omega the decoder gives out at one over one plus lambda: 0.333 for the three lambda-two rows, 0.250 for lambda three and 0.200 for lambda four, far below the 0.50 the codes are built for."><text x="26" y="24" font-size="9.4" font-weight="700">Whatever the code, the decoder is local</text>
<text x="26" y="36" font-size="7.4" fill="#4a5561">what one local block can see, and what it can fix</text>
<rect x="26" y="54" width="198.4" height="20" fill="#1546a0" opacity="0.18" stroke="currentColor" stroke-width="0.6"/>
<rect x="224.4" y="54" width="49.6" height="20" fill="#1b7a34" opacity="0.30" stroke="currentColor" stroke-width="0.6"/>
<text x="125.2" y="67" text-anchor="middle" font-size="7.0">the &#955;&#969; message symbols it covers</text>
<text x="249.2" y="67" text-anchor="middle" font-size="6.4" fill="#1b7a34" font-weight="700">&#961;</text>
<text x="26" y="48" font-size="7.2" font-weight="700">one local block&#8217;s support</text>
<text x="26" y="85" font-size="6.8" fill="#4a5561">n&#8320; = &#961; + &#955;&#969;</text>
<text x="26" y="108" font-size="7.4" fill="#1b1f24">It solves when its support holds at most &#961; erasures.</text>
<text x="26" y="120" font-size="7.4" fill="#1b1f24">At erasure rate x, about x&#183;n&#8320; of them are missing.</text>
<rect x="26" y="132" width="248" height="30" fill="none" stroke="#1546a0" stroke-width="0.9"/>
<text x="34" y="146" font-size="7.4" fill="#1546a0" font-weight="700">&#955;&#969;x + &#961;x &#8804; &#961;</text>
<text x="34" y="156" font-size="7.2" fill="#1b1f24">so it gives out at x = &#961;/n&#8320; = 1/(1+&#955;) when &#961; = &#969;.</text>
<text x="26" y="186" font-size="7.2" font-weight="700">row</text>
<text x="96" y="186" font-size="7.2" font-weight="700">n&#8320;</text>
<text x="152" y="186" font-size="7.2" font-weight="700">&#961;/n&#8320;</text>
<text x="212" y="186" font-size="7.2" font-weight="700">solve cost</text>
<line x1="26" y1="190" x2="274" y2="190" stroke="currentColor" stroke-width="0.6"/>
<text x="26" y="202" font-size="7.0">&#969;2048 &#955;2</text>
<text x="96" y="202" font-size="7.0">6144</text>
<text x="152" y="202" font-size="7.0" font-weight="700" fill="#1b7a34">0.333</text>
<text x="212" y="202" font-size="7.0">2048&#215;2048</text>
<text x="26" y="215" font-size="7.0">&#969;1024 &#955;2</text>
<text x="96" y="215" font-size="7.0">3072</text>
<text x="152" y="215" font-size="7.0" font-weight="700" fill="#1b7a34">0.333</text>
<text x="212" y="215" font-size="7.0">1024&#215;1024</text>
<text x="26" y="228" font-size="7.0">&#969;512 &#955;2</text>
<text x="96" y="228" font-size="7.0">1536</text>
<text x="152" y="228" font-size="7.0" font-weight="700" fill="#1b7a34">0.333</text>
<text x="212" y="228" font-size="7.0">512&#215;512</text>
<text x="26" y="241" font-size="7.0">&#969;1024 &#955;3</text>
<text x="96" y="241" font-size="7.0">4096</text>
<text x="152" y="241" font-size="7.0" font-weight="700" fill="#1b7a34">0.250</text>
<text x="212" y="241" font-size="7.0">1024&#215;1024</text>
<text x="26" y="254" font-size="7.0">&#969;1024 &#955;4</text>
<text x="96" y="254" font-size="7.0">5120</text>
<text x="152" y="254" font-size="7.0" font-weight="700" fill="#1b7a34">0.200</text>
<text x="212" y="254" font-size="7.0">1024&#215;1024</text>
<rect x="26" y="266" width="248" height="46" fill="none" stroke="#c62828" stroke-width="0.9"/>
<text x="34" y="280" font-size="7.2" font-weight="700" fill="#c62828">The gap is the decoder, not the code.</text>
<text x="34" y="291" font-size="7.0" fill="#1b1f24">Even the MDS rows (&#969;2048 &#955;2, &#969;1024 &#955;4) stop here;</text>
<text x="34" y="302" font-size="7.0" fill="#1b1f24">measured thresholds sit just above, at 0.336&#8211;0.349, 0.255, 0.204.</text></svg>
<figcaption>Why the measured tolerance is far below 0.50 anyway. <code>DecCBC[2]</code> solves one block at a time, and a block succeeds only when its own support &#8212; its &#961; parity symbols plus the &#955;&#969; message symbols it covers &#8212; holds at most &#961; erasures. Solving &#955;&#969;<em>x</em> + &#961;<em>x</em> &#8804; &#961; gives <em>x</em> &#8804; &#961;/n&#8320; = 1/(1+&#955;) when &#961; = &#969;, and the measurements land just above it: 0.336&#8211;0.349 for &#955; = 2, 0.255 for &#955; = 3 and 0.204 for &#955; = 4, the small excess coming from the cascade across blocks. That limit holds even for the two MDS rows, whose code alone could survive half the codeword. Because the local system is a Vandermonde matrix in distinct evaluation points it can be solved in &#961;&#178; rather than &#961;&#179; time &#8212; which is what makes &#969; = 1024 and 2048 measurable at all.</figcaption>
</figure>

