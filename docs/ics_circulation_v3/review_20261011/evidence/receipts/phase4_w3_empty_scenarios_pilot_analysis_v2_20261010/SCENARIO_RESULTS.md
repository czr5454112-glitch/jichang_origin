# Public-forecast scenario control: full development result

Audit: 29,619 checks, 0 errors; 58 bound files unchanged: True.

|Policy|J|On time|Completed|vs point better/equal/worse|vs legacy better/equal/worse|Invocation CPU s|Physical proxy calls|
|---|---:|---:|---:|---|---|---:|---:|
|point|28.400|20|24/24|0/4/0|0/4/0|24.00|166|
|scenario8_s17|32.400|20|24/24|0/2/2|0/2/2|122.72|907|
|scenario8_s29|32.400|20|24/24|0/3/1|0/3/1|125.50|913|
|scenario8_s43|28.400|20|24/24|0/4/0|0/4/0|116.17|860|

All three fixed seeds are reported. Each comparison uses all 36 paired existing tapes in a formal run, four nominal tapes in a pilot. No selection of best seed or efficacy subset.

- 36 reused synthetic development tapes; three sampling seeds are not independent operating days
- Prior uncalibrated, scenario sampling error does not bound model error
- Actions still generated from point public demand, scenario count does not enlarge action family
- Inherited generic claim says one_public_proxy; scenario-specific action_objective and nested physical records define the actual eight-draw mean
- Proxy row CPU excludes sampling/hash overhead; deployment and invocation CPU include it
