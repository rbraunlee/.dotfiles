"""Contract for the owner-facing, package-local supported helper reference."""

import re
import unittest
from pathlib import Path


REFERENCE = Path(__file__).resolve().parents[3] / "common/zsh/README.md"


class HelperReferenceTests(unittest.TestCase):
    def test_supported_names_and_acceptance_evidence_are_discoverable(self):
        reference = REFERENCE.read_text()
        names = (
            "v vim reload nz nb nf la ll df free psa psgrep jctl sysfailed audio ex "
            "sps spr sprs spqo spsii depends update upd upall upa rip riplong "
            "list listt listaur big cleanup mirror mirrord mirrors mirrora mirrorx "
            "mirrorxx ram rams yta-aac yta-best yta-flac yta-mp3 ytv-best "
            "wsimplescreen wsimplescreenrecorder btrfsfs btrfsli snapli snapcr "
            "snapch npacman nmirrorlist narcomirrorlist ngrub nmkinitcpio nfstab "
            "nhosts nhostname nresolv nnsswitch nsamba ngnupgconf nvconsole nsddm "
            "nsddmk nlxdm nlightdm nplymouth"
        ).split()
        for name in names:
            with self.subTest(name=name):
                self.assertRegex(reference, rf"`{re.escape(name)}`")
        for criterion in range(1, 13):
            with self.subTest(criterion=criterion):
                self.assertRegex(reference, rf"\| Z{criterion} \|")


if __name__ == "__main__":
    unittest.main()
