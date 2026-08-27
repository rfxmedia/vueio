# Third-party software in Vueio

Vueio release images include third-party operating-system packages, language
libraries, media codecs, and the bundled English transcription model. Those
components remain governed by their own licenses.

Each GitHub release includes architecture-specific SPDX SBOMs for the engine
and UI images. The SBOMs are the exact version inventory for that immutable
release and include package URLs that identify the corresponding source.

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

Corresponding source for an exact SBOM version is available through the
package URL recorded in that SBOM. The upstream source archives are maintained
by the package ecosystems used to build the release:

- Debian source packages: <https://sources.debian.org/>
- Alpine package sources: <https://gitlab.alpinelinux.org/alpine/aports>
- Python source distributions: <https://pypi.org/>
- npm package sources: <https://www.npmjs.com/>

These directions are published beside every binary release so recipients can
locate the source matching the exact component version they received.
