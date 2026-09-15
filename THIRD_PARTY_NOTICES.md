# Third-party software in Vueio

Vueio release images include third-party operating-system packages, language
libraries, media codecs, and the bundled English transcription model. Those
components remain governed by their own licenses.

Each GitHub release includes architecture-specific SPDX SBOMs for the engine
and UI images. The SBOMs record the package versions for that immutable release.
Package URLs identify their source ecosystems. For the FFmpeg build, use the
exact source archive and build recipe described below.

The images retain the license material supplied by their package distributors:

- UI JavaScript notices are available at `/THIRD_PARTY_NOTICES.txt` in every
  running Vueio installation and at the same path inside the UI image.
- Python package licenses remain in each package's `.dist-info/licenses`
  directory inside the engine image.
- Debian package copyright and license files remain under `/usr/share/doc`
  inside the engine image.
- Alpine package licenses remain under `/usr/share/licenses` inside the UI
  image.
- The Moonshine model license is stored beside the model as
  `/app/moonshine-models/MOONSHINE_LICENSE.txt` in the engine image.
- FFmpeg is built from its unmodified, checksum-pinned upstream release.
  Its exact source archive, license files, build configuration, and NVIDIA
  codec-header notice are in `/usr/share/doc/ffmpeg` in the engine image.
  `backend/Dockerfile` contains the build recipe. The installed `ffmpeg`
  package records the upstream version and the Vueio packaging revision.

For distributor-supplied packages, use the package URL and version recorded in
the SBOM to find the corresponding source. These source archives are maintained
by the package ecosystems used to build the release:

- Debian source packages: <https://sources.debian.org/>
- Alpine package sources: <https://gitlab.alpinelinux.org/alpine/aports>
- Python source distributions: <https://pypi.org/>
- npm package sources: <https://www.npmjs.com/>

These directions are published beside every binary release so recipients can
locate the source matching the exact component version they received.

## FFmpeg build

The engine uses [FFmpeg 9.0.1](https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz).
The SHA-256 digest is
`cf38e0e28c7e5605942c4a77755349b0145804a397af37eb1fb4c77cb237f635`.
This build enables GPL codecs. FFmpeg remains a separate executable; its
license does not replace the Vueio application license. Debian supplies the
external codec libraries and NVIDIA headers. Their notices identify the
matching source packages.

The build retains file decoders, CPU encoding, NVIDIA NVENC/NVDEC, and VA-API.
It does not include desktop playback, camera capture, or optional broadcast
services. Vueio does not use those features. CPU processing remains the default.
