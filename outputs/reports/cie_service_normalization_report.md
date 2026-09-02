# CIE service-rate normalization three-arm audit

Executed input runs discovered: **12** (expected 12).
Complete matched map/control groups: **4/4**.

## Exact arm semantics

- `RAW_COUNT_AS_SECONDS`: full mask 15 and raw Q/I counts.
- `SERVICE_RATE_NORMALIZED`: full mask 15 and the existing `service_rate_normalized` Q/I scaling.
- `NO_QI_BUT_CALENDAR`: mask 12, which removes Q/I while retaining corridor-calendar and target-service-calendar waits. Direct-neighbour calendar visibility and physical service calendars remain enabled.
- `SERVICE_X2` comes only from the frozen manifest multiplier 2.0; topology, tasks, release, and all other G31 controls stay fixed.

## Fixed comparisons

Each pair status is evaluated independently after the common three-arm identity and integrity gate.

| Map | Service | Metric | Normalized pair status | No-Q/I pair status | Raw | Normalized | No Q/I | Norm - raw | No Q/I - raw |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| map2 | REAL_SERVICE | completed segments | COMPLETE | COMPLETE | 43603 | 43603 | 43603 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | completed raw bags | COMPLETE | COMPLETE | 28506 | 28506 | 28506 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | raw-bag completion rate | COMPLETE | COMPLETE | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | population latency minimum (s) | COMPLETE | COMPLETE | 188.0009999999893 | 188.0009999999893 | 188.0009999999893 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | population latency mean (s) | COMPLETE | COMPLETE | 237.41280897039394 | 237.41280897039394 | 238.15899186311827 | 0.0 | 0.7461828927243346 |
| map2 | REAL_SERVICE | population latency P95 (s) | COMPLETE | COMPLETE | 339.7229675000199 | 339.7229675000199 | 343.8852825000322 | 0.0 | 4.162315000012313 |
| map2 | REAL_SERVICE | population latency P99 (s) | COMPLETE | COMPLETE | 401.8339754999956 | 401.8339754999956 | 409.5132989999946 | 0.0 | 7.679323499999043 |
| map2 | REAL_SERVICE | population latency maximum (s) | COMPLETE | COMPLETE | 527.0250299999898 | 527.0250299999898 | 558.894269999997 | 0.0 | 31.869240000007267 |
| map2 | REAL_SERVICE | on-time raw bags | COMPLETE | COMPLETE | 28506 | 28506 | 28506 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | on-time raw-bag rate | COMPLETE | COMPLETE | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | missed raw bags | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | missed raw-bag rate | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | fixed-horizon all-population tardiness sum (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | fixed-horizon all-population tardiness mean (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | fixed-horizon all-population tardiness P95 (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | fixed-horizon all-population tardiness P99 (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | fixed-horizon all-population tardiness maximum (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | time to 90% completion (s) | COMPLETE | COMPLETE | 62870.60591700002 | 62870.60591700002 | 62870.60591700002 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | time to 95% completion (s) | COMPLETE | COMPLETE | 67288.13779700002 | 67288.13779700002 | 67288.13779700002 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | time to 99% completion (s) | COMPLETE | COMPLETE | 71122.43991700003 | 71122.43991700003 | 71122.43991700003 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | raw-bag total backlog area (bag-s) | COMPLETE | COMPLETE | 70149629.17620328 | 70149629.17620328 | 70152487.2221336 | 0.0 | 2858.045930325985 |
| map2 | REAL_SERVICE | raw-bag total backlog peak | COMPLETE | COMPLETE | 2340 | 2340 | 2340 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | raw-bag total backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | raw-bag source backlog area (bag-s) | COMPLETE | COMPLETE | 64163634.43424304 | 64163634.43424304 | 64163634.43424304 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | raw-bag source backlog peak | COMPLETE | COMPLETE | 2194 | 2194 | 2194 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | raw-bag source backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | raw-bag network backlog area (bag-s) | COMPLETE | COMPLETE | 5985994.741960001 | 5985994.741960001 | 5988852.787889996 | 0.0 | 2858.045929994434 |
| map2 | REAL_SERVICE | raw-bag network backlog peak | COMPLETE | COMPLETE | 463 | 463 | 463 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | raw-bag network backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| map2 | REAL_SERVICE | native event count | COMPLETE | COMPLETE | 3997648 | 3997648 | 4007115 | 0.0 | 9467.0 |
| map2 | REAL_SERVICE | native decision count | COMPLETE | COMPLETE | 336638 | 336638 | 336770 | 0.0 | 132.0 |
| map2 | REAL_SERVICE | wall time (s) | COMPLETE | COMPLETE | 21.798478099983186 | 25.03746939986013 | 24.44766079983674 | 3.2389912998769432 | 2.6491826998535544 |
| map2 | REAL_SERVICE | CPU time (s) | COMPLETE | COMPLETE | 21.15625 | 24.65625 | 23.921875 | 3.5 | 2.765625 |
| map2 | SERVICE_X2 | completed segments | COMPLETE | COMPLETE | 43603 | 43603 | 43603 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | completed raw bags | COMPLETE | COMPLETE | 28506 | 28506 | 28506 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | raw-bag completion rate | COMPLETE | COMPLETE | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | population latency minimum (s) | COMPLETE | COMPLETE | 196.00099999999657 | 196.00099999999657 | 196.00099999999657 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | population latency mean (s) | COMPLETE | COMPLETE | 710.6695257437045 | 534.0530786230985 | 694.7185909675172 | -176.61644712060604 | -15.950934776187296 |
| map2 | SERVICE_X2 | population latency P95 (s) | COMPLETE | COMPLETE | 4139.705089999992 | 2539.3800274999903 | 3859.3433649999906 | -1600.3250625000019 | -280.36172500000157 |
| map2 | SERVICE_X2 | population latency P99 (s) | COMPLETE | COMPLETE | 6184.456426999998 | 4200.128243999992 | 6393.249240499998 | -1984.328183000006 | 208.7928135000002 |
| map2 | SERVICE_X2 | population latency maximum (s) | COMPLETE | COMPLETE | 6625.7403599999925 | 4633.524789999996 | 6832.281929999994 | -1992.2155699999967 | 206.54157000000123 |
| map2 | SERVICE_X2 | on-time raw bags | COMPLETE | COMPLETE | 28371 | 28475 | 28416 | 104.0 | 45.0 |
| map2 | SERVICE_X2 | on-time raw-bag rate | COMPLETE | COMPLETE | 0.9952641549147548 | 0.9989125096470919 | 0.9968427699431699 | 0.0036483547323370447 | 0.0015786150284150535 |
| map2 | SERVICE_X2 | missed raw bags | COMPLETE | COMPLETE | 135 | 31 | 90 | -104.0 | -45.0 |
| map2 | SERVICE_X2 | missed raw-bag rate | COMPLETE | COMPLETE | 0.004735845085245161 | 0.001087490352908116 | 0.003157230056830107 | -0.0036483547323370447 | -0.0015786150284150535 |
| map2 | SERVICE_X2 | fixed-horizon all-population tardiness sum (s) | COMPLETE | COMPLETE | 127281.17201999982 | 9454.19262999995 | 49680.97680999983 | -117826.97938999988 | -77600.19520999999 |
| map2 | SERVICE_X2 | fixed-horizon all-population tardiness mean (s) | COMPLETE | COMPLETE | 4.465066021890122 | 0.3316562348277538 | 1.7428252581912522 | -4.1334097870623685 | -2.7222407636988697 |
| map2 | SERVICE_X2 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | fixed-horizon all-population tardiness maximum (s) | COMPLETE | COMPLETE | 2560.8798899999965 | 772.2130899999975 | 2750.1884900000005 | -1788.666799999999 | 189.30860000000393 |
| map2 | SERVICE_X2 | time to 90% completion (s) | COMPLETE | COMPLETE | 63166.24329700002 | 63041.482957000015 | 63160.24329700002 | -124.760340000008 | -6.0 |
| map2 | SERVICE_X2 | time to 95% completion (s) | COMPLETE | COMPLETE | 67300.13779700002 | 67300.13779700002 | 67300.13779700002 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | time to 99% completion (s) | COMPLETE | COMPLETE | 71130.43991700003 | 71130.43991700003 | 71130.43991700003 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | raw-bag total backlog area (bag-s) | COMPLETE | COMPLETE | 75369618.25841275 | 73400620.06274197 | 75083785.03231311 | -1968998.1956707835 | -285833.22609964013 |
| map2 | SERVICE_X2 | raw-bag total backlog peak | COMPLETE | COMPLETE | 2490 | 2458 | 2468 | -32.0 | -22.0 |
| map2 | SERVICE_X2 | raw-bag total backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | raw-bag source backlog area (bag-s) | COMPLETE | COMPLETE | 64163634.43424304 | 64163634.43424304 | 64163634.43424304 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | raw-bag source backlog peak | COMPLETE | COMPLETE | 2194 | 2194 | 2194 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | raw-bag source backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | raw-bag network backlog area (bag-s) | COMPLETE | COMPLETE | 11205983.824170109 | 9236985.628500156 | 10920150.598070167 | -1968998.1956699528 | -285833.2260999419 |
| map2 | SERVICE_X2 | raw-bag network backlog peak | COMPLETE | COMPLETE | 1211 | 812 | 1173 | -399.0 | -38.0 |
| map2 | SERVICE_X2 | raw-bag network backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| map2 | SERVICE_X2 | native event count | COMPLETE | COMPLETE | 4466366 | 4426978 | 4515093 | -39388.0 | 48727.0 |
| map2 | SERVICE_X2 | native decision count | COMPLETE | COMPLETE | 333780 | 333070 | 334894 | -710.0 | 1114.0 |
| map2 | SERVICE_X2 | wall time (s) | COMPLETE | COMPLETE | 36.158935399958864 | 33.60944569995627 | 36.57205790001899 | -2.549489700002596 | 0.4131225000601262 |
| map2 | SERVICE_X2 | CPU time (s) | COMPLETE | COMPLETE | 35.5625 | 33.125 | 35.890625 | -2.4375 | 0.328125 |
| nanning | REAL_SERVICE | completed segments | COMPLETE | COMPLETE | 43603 | 43603 | 43603 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | completed raw bags | COMPLETE | COMPLETE | 28506 | 28506 | 28506 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | raw-bag completion rate | COMPLETE | COMPLETE | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | population latency minimum (s) | COMPLETE | COMPLETE | 48.40099999999802 | 48.40099999999802 | 48.40099999999802 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | population latency mean (s) | COMPLETE | COMPLETE | 616.0590019659043 | 637.1994650887555 | 604.5154681168905 | 21.1404631228512 | -11.543533849013784 |
| nanning | REAL_SERVICE | population latency P95 (s) | COMPLETE | COMPLETE | 2378.668284999999 | 2505.7241275000006 | 2273.731824999998 | 127.05584250000175 | -104.9364600000008 |
| nanning | REAL_SERVICE | population latency P99 (s) | COMPLETE | COMPLETE | 2781.375951500004 | 2919.615694000003 | 2665.1375894999965 | 138.239742499999 | -116.23836200000733 |
| nanning | REAL_SERVICE | population latency maximum (s) | COMPLETE | COMPLETE | 4642.761409999999 | 4937.776789999993 | 4680.665319999993 | 295.01537999999346 | 37.90390999999363 |
| nanning | REAL_SERVICE | on-time raw bags | COMPLETE | COMPLETE | 28395 | 28221 | 28442 | -174.0 | 47.0 |
| nanning | REAL_SERVICE | on-time raw-bag rate | COMPLETE | COMPLETE | 0.9961060829299095 | 0.9900021048200379 | 0.9977548586262541 | -0.006103978109871622 | 0.0016487756963445843 |
| nanning | REAL_SERVICE | missed raw bags | COMPLETE | COMPLETE | 111 | 285 | 64 | 174.0 | -47.0 |
| nanning | REAL_SERVICE | missed raw-bag rate | COMPLETE | COMPLETE | 0.003893917070090458 | 0.00999789517996208 | 0.0022451413737458736 | 0.006103978109871622 | -0.0016487756963445843 |
| nanning | REAL_SERVICE | fixed-horizon all-population tardiness sum (s) | COMPLETE | COMPLETE | 33334.62352999991 | 58631.30290000005 | 23242.36185999993 | 25296.679370000144 | -10092.261669999978 |
| nanning | REAL_SERVICE | fixed-horizon all-population tardiness mean (s) | COMPLETE | COMPLETE | 1.1693897260225885 | 2.0568056865221376 | 0.8153498161790477 | 0.8874159604995491 | -0.35403990984354083 |
| nanning | REAL_SERVICE | fixed-horizon all-population tardiness P95 (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | fixed-horizon all-population tardiness P99 (s) | COMPLETE | COMPLETE | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | fixed-horizon all-population tardiness maximum (s) | COMPLETE | COMPLETE | 1362.3005799999955 | 1447.8447099999976 | 1195.8705799999989 | 85.54413000000204 | -166.42999999999665 |
| nanning | REAL_SERVICE | time to 90% completion (s) | COMPLETE | COMPLETE | 63105.37530700001 | 63105.37530700001 | 63102.05997700001 | 0.0 | -3.31532999999763 |
| nanning | REAL_SERVICE | time to 95% completion (s) | COMPLETE | COMPLETE | 67257.76474700002 | 67260.36474700001 | 67257.76474700002 | 2.599999999991269 | 0.0 |
| nanning | REAL_SERVICE | time to 99% completion (s) | COMPLETE | COMPLETE | 71068.39389700002 | 71070.74589700002 | 71068.39389700002 | 2.3519999999989523 | 0.0 |
| nanning | REAL_SERVICE | raw-bag total backlog area (bag-s) | COMPLETE | COMPLETE | 78661157.36828311 | 79221925.23089322 | 78342718.01216222 | 560767.8626101166 | -318439.3561208844 |
| nanning | REAL_SERVICE | raw-bag total backlog peak | COMPLETE | COMPLETE | 2756 | 2777 | 2757 | 21.0 | 1.0 |
| nanning | REAL_SERVICE | raw-bag total backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | raw-bag source backlog area (bag-s) | COMPLETE | COMPLETE | 64215157.65717326 | 64215022.399203256 | 64215029.97770327 | -135.25797000527382 | -127.67946998775005 |
| nanning | REAL_SERVICE | raw-bag source backlog peak | COMPLETE | COMPLETE | 2194 | 2194 | 2194 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | raw-bag source backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | raw-bag network backlog area (bag-s) | COMPLETE | COMPLETE | 14445999.711110031 | 15006902.831690155 | 14127688.034460096 | 560903.1205801237 | -318311.67664993554 |
| nanning | REAL_SERVICE | raw-bag network backlog peak | COMPLETE | COMPLETE | 1580 | 1618 | 1554 | 38.0 | -26.0 |
| nanning | REAL_SERVICE | raw-bag network backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| nanning | REAL_SERVICE | native event count | COMPLETE | COMPLETE | 7087605 | 7156766 | 6712155 | 69161.0 | -375450.0 |
| nanning | REAL_SERVICE | native decision count | COMPLETE | COMPLETE | 588936 | 595168 | 553606 | 6232.0 | -35330.0 |
| nanning | REAL_SERVICE | wall time (s) | COMPLETE | COMPLETE | 53.45794479991309 | 52.89454449992627 | 52.8991322000511 | -0.5634002999868244 | -0.5588125998619944 |
| nanning | REAL_SERVICE | CPU time (s) | COMPLETE | COMPLETE | 52.46875 | 52.0625 | 51.875 | -0.40625 | -0.59375 |
| nanning | SERVICE_X2 | completed segments | COMPLETE | COMPLETE | 43603 | 43602 | 43603 | -1.0 | 0.0 |
| nanning | SERVICE_X2 | completed raw bags | COMPLETE | COMPLETE | 28506 | 28505 | 28506 | -1.0 | 0.0 |
| nanning | SERVICE_X2 | raw-bag completion rate | COMPLETE | COMPLETE | 1.0 | 0.9999649196660352 | 1.0 | -3.508033396482091e-05 | 0.0 |
| nanning | SERVICE_X2 | population latency minimum (s) | N_M_METRIC_NOT_AVAILABLE (SERVICE_RATE_NORMALIZED) | COMPLETE | 54.40099999999802 | N/M | 54.40099999999802 | N/M | 0.0 |
| nanning | SERVICE_X2 | population latency mean (s) | N_M_METRIC_NOT_AVAILABLE (SERVICE_RATE_NORMALIZED) | COMPLETE | 14440.259826714415 | N/M | 13166.305253109884 | N/M | -1273.954573604531 |
| nanning | SERVICE_X2 | population latency P95 (s) | N_M_METRIC_NOT_AVAILABLE (SERVICE_RATE_NORMALIZED) | COMPLETE | 47422.98673750003 | N/M | 46326.55906250004 | N/M | -1096.4276749999917 |
| nanning | SERVICE_X2 | population latency P99 (s) | N_M_METRIC_NOT_AVAILABLE (SERVICE_RATE_NORMALIZED) | COMPLETE | 52578.42171350007 | N/M | 52376.57695200003 | N/M | -201.84476150004048 |
| nanning | SERVICE_X2 | population latency maximum (s) | N_M_METRIC_NOT_AVAILABLE (SERVICE_RATE_NORMALIZED) | COMPLETE | 55413.71196000024 | N/M | 55426.56617000006 | N/M | 12.854209999815794 |
| nanning | SERVICE_X2 | on-time raw bags | COMPLETE | COMPLETE | 10400 | 10471 | 10165 | 71.0 | -235.0 |
| nanning | SERVICE_X2 | on-time raw-bag rate | COMPLETE | COMPLETE | 0.3648354732337052 | 0.36732617694520453 | 0.35659159475198204 | 0.0024907037114993424 | -0.008243878481723144 |
| nanning | SERVICE_X2 | missed raw bags | COMPLETE | COMPLETE | 18106 | 18035 | 18341 | -71.0 | 235.0 |
| nanning | SERVICE_X2 | missed raw-bag rate | COMPLETE | COMPLETE | 0.6351645267662949 | 0.6326738230547955 | 0.643408405248018 | -0.002490703711499398 | 0.008243878481723144 |
| nanning | SERVICE_X2 | fixed-horizon all-population tardiness sum (s) | COMPLETE | COMPLETE | 266818183.19624093 | 270399569.92262065 | 239771940.7295703 | 3581386.7263797224 | -27046242.466670632 |
| nanning | SERVICE_X2 | fixed-horizon all-population tardiness mean (s) | COMPLETE | COMPLETE | 9360.070974399809 | 9485.707216818237 | 8411.279756176606 | 125.63624241842808 | -948.791218223203 |
| nanning | SERVICE_X2 | fixed-horizon all-population tardiness P95 (s) | COMPLETE | COMPLETE | 28887.177937500008 | 27430.904547500097 | 30943.16837000003 | -1456.2733899999112 | 2055.9904325000207 |
| nanning | SERVICE_X2 | fixed-horizon all-population tardiness P99 (s) | COMPLETE | COMPLETE | 39724.12984550024 | 40307.82178050005 | 41757.27537000005 | 583.6919349998134 | 2033.145524499807 |
| nanning | SERVICE_X2 | fixed-horizon all-population tardiness maximum (s) | COMPLETE | COMPLETE | 51990.43237000024 | 51886.90170000013 | 51868.23537000005 | -103.53067000010924 | -122.19700000018929 |
| nanning | SERVICE_X2 | time to 90% completion (s) | COMPLETE | COMPLETE | 79477.74291700017 | 80246.73024700015 | 77717.32991700005 | 768.9873299999745 | -1760.4130000001169 |
| nanning | SERVICE_X2 | time to 95% completion (s) | COMPLETE | COMPLETE | 83788.96491700024 | 84743.52224700013 | 81420.01791700005 | 954.5573299998941 | -2368.9470000001893 |
| nanning | SERVICE_X2 | time to 99% completion (s) | COMPLETE | COMPLETE | 87719.37091700024 | 88805.40224700012 | 86024.54991700005 | 1086.0313299998816 | -1694.8210000001854 |
| nanning | SERVICE_X2 | raw-bag total backlog area (bag-s) | COMPLETE | COMPLETE | 388322070.2802291 | 391911237.17666954 | 363284286.8144941 | 3589166.8964404464 | -25037783.46573502 |
| nanning | SERVICE_X2 | raw-bag total backlog peak | COMPLETE | COMPLETE | 7558 | 7558 | 7189 | 0.0 | -369.0 |
| nanning | SERVICE_X2 | raw-bag total backlog at horizon end | COMPLETE | COMPLETE | 0 | 1 | 0 | 1.0 | 0.0 |
| nanning | SERVICE_X2 | raw-bag source backlog area (bag-s) | COMPLETE | COMPLETE | 66350499.549172774 | 66348504.125792794 | 66353353.3265028 | -1995.4233799800277 | 2853.7773300260305 |
| nanning | SERVICE_X2 | raw-bag source backlog peak | COMPLETE | COMPLETE | 2249 | 2249 | 2249 | 0.0 | 0.0 |
| nanning | SERVICE_X2 | raw-bag source backlog at horizon end | COMPLETE | COMPLETE | 0 | 0 | 0 | 0.0 | 0.0 |
| nanning | SERVICE_X2 | raw-bag network backlog area (bag-s) | COMPLETE | COMPLETE | 321971570.73105216 | 325562733.0508812 | 296930933.48798877 | 3591162.3198290467 | -25040637.24306339 |
| nanning | SERVICE_X2 | raw-bag network backlog peak | COMPLETE | COMPLETE | 6971 | 6882 | 6561 | -89.0 | -410.0 |
| nanning | SERVICE_X2 | raw-bag network backlog at horizon end | COMPLETE | COMPLETE | 0 | 1 | 0 | 1.0 | 0.0 |
| nanning | SERVICE_X2 | native event count | COMPLETE | COMPLETE | 8326813 | 8449040 | 8183685 | 122227.0 | -143128.0 |
| nanning | SERVICE_X2 | native decision count | COMPLETE | COMPLETE | 547660 | 569287 | 544317 | 21627.0 | -3343.0 |
| nanning | SERVICE_X2 | wall time (s) | COMPLETE | COMPLETE | 272.80279350001365 | 268.6698076999746 | 231.5746176999528 | -4.132985800039023 | -41.22817580006085 |
| nanning | SERVICE_X2 | CPU time (s) | COMPLETE | COMPLETE | 267.859375 | 263.484375 | 226.96875 | -4.375 | -40.890625 |

## Interpretation boundary

No incomplete timing cell is replaced by survivor timing; no survivor/common cohort is used. This aggregate consumes the fixed-horizon backlog correction view from the common extractor; legacy incomplete last-event areas are never used without an exact tail reconstruction, and ambiguous tails are N/M. The standalone correction supplement retains legacy values and methods. This aggregate does not select a winning arm or tune a parameter. A general service-normalization claim requires attributable, directionally consistent evidence on both real maps and the pre-specified service-pressure-enhancement control; otherwise the pre-specified stopping conclusion applies.
