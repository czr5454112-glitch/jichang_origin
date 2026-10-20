G31 delivery ZIP parts

The original complete ZIP remains at the producer's original local path.
This directory is an exact byte split for Git publication, not a new evidence
package. No part exceeds 64MiB. No Git LFS or network operation was used.

Archive: G31_INVENTORY_SPI_PARTIAL_DELIVERY_20261021.zip
Archive bytes: 314360446
Archive SHA256: 59bd99f72da9031079540fccc24fb9083f6ebf700ffbb2004f2b0712e4f28a1d
Manifest SHA256: 784c03dca3a1e67f97d359c45e787d4665c455313398eca480b6a8e2adee526e
Reassembler SHA256: 349d8823e71c0c037a43b939ffbe30244eeb349960e49f2b5c6bf3eff7846714

Download parts_manifest.json, all archive.partNNNN files and
reassemble_partial_delivery_001.py from the same published revision. Obtain the trusted
expected manifest SHA from the separately supplied delivery receipt. Do not
mix revisions, skip a part, concatenate GitHub HTML pages or treat a failed
download as an empty part.

With Python3.11 and the standard library, from the downloaded directory:
  python -I -B reassemble_partial_delivery_001.py --manifest parts_manifest.json --manifest-sha256 784c03dca3a1e67f97d359c45e787d4665c455313398eca480b6a8e2adee526e --output "NEW_COMPLETE_DELIVERY.zip"

The output must not already exist and its parent directory must exist. Every
part is checked before output creation and again during copying. The saved
ZIP must match the original full bytes and SHA. Success prints status
verified_complete_archive. An error leaves any incomplete new output in place;
do not use or rename it as a verified archive, and do not overwrite evidence.

Reassembly does not extract the archive or establish scientific acceptance.
After a successful full ZIP check, follow the outer delivery README's Windows
Python3.11 deep-directory isolated audit. Its report and the ZIP's own SHA
remain outside evidence/; the existing exact CAS package is not modified.
