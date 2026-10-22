"""Scanner packs.

Flutter (plus Android / iOS / pub.dev / package outdated checks that a Flutter
app needs) is the **reference implementation**. Other major frameworks can land
later as sibling modules that feed the same report and requirements pipeline.
Importing this package does not run any checks.
"""

from vigil.scanners.android import AndroidSdk, SdkPin, parse_gradle, read_android
from vigil.scanners.expiries import Expiry, check_expiries, load_expiries
from vigil.scanners.flutter import FlutterInfo, read_flutter
from vigil.scanners.ios import IosTargets, read_ios
from vigil.scanners.packages import OutdatedPackage, read_lock, run_outdated
from vigil.scanners.pubdev import PubInfo

__all__ = [
    "AndroidSdk",
    "Expiry",
    "FlutterInfo",
    "IosTargets",
    "OutdatedPackage",
    "PubInfo",
    "SdkPin",
    "check_expiries",
    "load_expiries",
    "parse_gradle",
    "read_android",
    "read_flutter",
    "read_ios",
    "read_lock",
    "run_outdated",
]
