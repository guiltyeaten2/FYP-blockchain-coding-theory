# Methodology and validation

Referenced from the method chapter rather than the results.

## 01-decoder-correctness-fix

*Goes in: Methodology — validation*

**Question.** Why does this project verify recovered bytes rather than trusting the decoder's own success flag?

**Data.** A historical run at omega=rho=lambda=2, mu=2048 - a parameterisation the main sweep does not cover - with the same 40 trials (ten each at 5%, 15%, 25% and 45% erasure) put through the decoder before and after a correctness fix. decoder_fix_results.json.

**Shows.** Before the fix the decoder claimed success on all 40 trials and was wrong on 31 of them; it never once reported a failure. After, silent corruption is zero and correct recoveries rose from 9 to 16 - the old decoder had been poisoning positions with fabricated zeros that blocked later rounds from resolving them.

