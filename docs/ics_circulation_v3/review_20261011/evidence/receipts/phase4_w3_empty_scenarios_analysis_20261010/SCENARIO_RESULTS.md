# Public-forecast scenario control: full development result

Audit: 343,993 checks, 0 errors; 218 bound files unchanged: True.

|Policy|J|On time|Completed|vs point better/equal/worse|vs legacy better/equal/worse|Invocation CPU s|Physical proxy calls|
|---|---:|---:|---:|---|---|---:|---:|
|point|370.500|166|198/198|0/36/0|0/35/1|367.33|2070|
|scenario8_s17|384.700|167|198/198|3/20/13|2/20/14|1855.45|10204|
|scenario8_s29|364.300|168|198/198|3/30/3|2/31/3|1760.62|10236|
|scenario8_s43|367.500|167|198/198|2/34/0|1/35/0|1710.77|9850|

All three fixed seeds are reported. Each comparison uses all 36 paired existing tapes in a formal run, four nominal tapes in a pilot. No selection of best seed or efficacy subset.

- 36 reused synthetic development tapes; three sampling seeds are not independent operating days
- Prior uncalibrated, scenario sampling error does not bound model error
- Actions still generated from point public demand, scenario count does not enlarge action family
- Inherited generic claim says one_public_proxy; scenario-specific action_objective and nested physical records define the actual eight-draw mean
- Proxy row CPU excludes sampling/hash overhead; deployment and invocation CPU include it
