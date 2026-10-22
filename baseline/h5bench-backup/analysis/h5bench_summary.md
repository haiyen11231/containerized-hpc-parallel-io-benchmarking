# h5bench summary

Rates in GiB/s (h5bench's binary units normalized). `trustworthy=FALSE` marks warm reads, which were served from page cache and never reached Lustre.


## intra_node

| config | variant | op | cache | n | mean GiB/s | 95% CI | rel CI | use |
|---|---|---|---|---|---|---|---|---|
| contig_contig | native | write | n/a | 10 | 1.0862 | 0.0477 | 4.4% | yes |
| contig_contig | container | write | n/a | 10 | 1.0273 | 0.1222 | 11.9% | yes |
| contig_interleaved | native | write | n/a | 10 | 0.1793 | 0.0027 | 1.5% | yes |
| contig_interleaved | container | write | n/a | 10 | 0.182 | 0.0038 | 2.1% | yes |
| interleaved_contig | native | write | n/a | 10 | 0.7106 | 0.0762 | 10.7% | yes |
| interleaved_contig | container | write | n/a | 10 | 0.6522 | 0.1164 | 17.8% | yes |
| interleaved_interleaved | native | write | n/a | 10 | 1.0356 | 0.0919 | 8.9% | yes |
| interleaved_interleaved | container | write | n/a | 10 | 1.1632 | 0.0789 | 6.8% | yes |

## weak_scaling

| config | variant | op | cache | n | mean GiB/s | 95% CI | rel CI | use |
|---|---|---|---|---|---|---|---|---|
| n1 | native | write | n/a | 10 | 1.0526 | 0.0635 | 6.0% | yes |
| n1 | native | read | warm | 10 | 71.5697 | 25.6403 | 35.8% | NO |
| n1 | native | read | cold | 10 | 6.6662 | 7.4737 | 112.1% | NO |
| n1 | container | write | n/a | 10 | 1.0958 | 0.1064 | 9.7% | yes |
| n1 | container | read | warm | 10 | 65.5046 | 25.3194 | 38.7% | NO |
| n1 | container | read | cold | 10 | 2.1309 | 0.1847 | 8.7% | yes |
| n2 | native | write | n/a | 10 | 1.1484 | 0.0844 | 7.3% | yes |
| n2 | native | read | warm | 10 | 3.658 | 0.2952 | 8.1% | NO |
| n2 | container | write | n/a | 10 | 1.2307 | 0.1358 | 11.0% | yes |
| n2 | container | read | warm | 10 | 3.8777 | 0.6244 | 16.1% | NO |
| n2 | container | read | cold | 10 | 3.3117 | 0.2288 | 6.9% | yes |
| n4 | native | write | n/a | 10 | 2.1527 | 0.1312 | 6.1% | yes |
| n4 | native | read | warm | 10 | 5.0439 | 0.4025 | 8.0% | NO |
| n4 | container | write | n/a | 10 | 2.2605 | 0.1303 | 5.8% | yes |
| n4 | container | read | warm | 10 | 5.502 | 0.4497 | 8.2% | NO |
| n8 | native | write | n/a | 10 | 2.589 | 0.2994 | 11.6% | yes |
| n8 | native | read | warm | 10 | 5.8105 | 0.7746 | 13.3% | NO |
| n8 | container | write | n/a | 10 | 2.6463 | 0.2808 | 10.6% | yes |
| n8 | container | read | warm | 10 | 6.034 | 0.7161 | 11.9% | NO |

## strong_scaling

| config | variant | op | cache | n | mean GiB/s | 95% CI | rel CI | use |
|---|---|---|---|---|---|---|---|---|
| n1 | native | write | n/a | 10 | 1.156 | 0.0687 | 5.9% | yes |
| n1 | native | read | warm | 10 | 80.0726 | 19.4141 | 24.2% | NO |
| n1 | container | write | n/a | 10 | 1.1569 | 0.0755 | 6.5% | yes |
| n1 | container | read | warm | 10 | 55.3181 | 31.8874 | 57.6% | NO |
| n2 | native | write | n/a | 10 | 1.3995 | 0.1712 | 12.2% | yes |
| n2 | native | read | warm | 10 | 4.2676 | 0.4035 | 9.5% | NO |
| n2 | container | write | n/a | 10 | 1.3813 | 0.0993 | 7.2% | yes |
| n2 | container | read | warm | 10 | 4.7692 | 0.4092 | 8.6% | NO |
| n4 | native | write | n/a | 10 | 1.2016 | 0.1582 | 13.2% | yes |
| n4 | native | read | warm | 10 | 4.8199 | 0.9216 | 19.1% | NO |
| n4 | container | write | n/a | 10 | 1.3753 | 0.2509 | 18.2% | yes |
| n4 | container | read | warm | 10 | 4.3107 | 0.6086 | 14.1% | NO |
| n8 | native | write | n/a | 10 | 0.9848 | 0.1552 | 15.8% | yes |
| n8 | native | read | warm | 10 | 4.326 | 0.8146 | 18.8% | NO |
| n8 | container | write | n/a | 10 | 0.8795 | 0.1019 | 11.6% | yes |
| n8 | container | read | warm | 10 | 3.5471 | 0.7596 | 21.4% | NO |

## collective_io

| config | variant | op | cache | n | mean GiB/s | 95% CI | rel CI | use |
|---|---|---|---|---|---|---|---|---|
| dno_mno | native | write | n/a | 10 | 1.516 | 0.1631 | 10.8% | yes |
| dno_mno | native | read | warm | 10 | 4.4164 | 0.6978 | 15.8% | NO |
| dno_mno | container | write | n/a | 10 | 1.5198 | 0.1618 | 10.6% | yes |
| dno_mno | container | read | warm | 10 | 5.3133 | 0.394 | 7.4% | NO |
| dno_myes | native | write | n/a | 10 | 1.5499 | 0.1027 | 6.6% | yes |
| dno_myes | native | read | warm | 10 | 4.6391 | 0.5335 | 11.5% | NO |
| dno_myes | container | write | n/a | 10 | 1.5177 | 0.1258 | 8.3% | yes |
| dno_myes | container | read | warm | 10 | 4.831 | 0.4546 | 9.4% | NO |
| dyes_mno | native | write | n/a | 10 | 1.6718 | 0.0475 | 2.8% | yes |
| dyes_mno | native | read | warm | 10 | 3.674 | 0.7755 | 21.1% | NO |
| dyes_mno | container | write | n/a | 10 | 1.8045 | 0.0556 | 3.1% | yes |
| dyes_mno | container | read | warm | 10 | 3.7954 | 0.6664 | 17.6% | NO |
| dyes_myes | native | write | n/a | 10 | 1.5101 | 0.1135 | 7.5% | yes |
| dyes_myes | native | read | warm | 10 | 3.9541 | 0.4386 | 11.1% | NO |
| dyes_myes | container | write | n/a | 10 | 1.8231 | 0.0578 | 3.2% | yes |
| dyes_myes | container | read | warm | 10 | 4.1996 | 0.4404 | 10.5% | NO |
