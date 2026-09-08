# DaVinci Resolve SDK lifecycle

This is a source preview; the npm package remains unpublished. The package remains `private: true`; no registry release is activated. The proposed package name `davinci-resolve-sdk` returned npm E404 on 2026-09-08. This is an observation, not a reservation. The independent source repository is jindratilk/davinci-resolve-sdk.

The complete inherited API and explicit subpaths are preserved at the 0.2.0 authoring baseline. Internal compatibility fields retain their historical names; the active distribution is `standalone_local`. Runtime negotiation still validates protocol, source identity and compatible version ranges.

A release requires standalone Free acceptance, an exact reviewed source/package inventory, reproducible source builds, dependency license notices and a deliberate public repository/package release decision. The client tarball alone does not include its companion Python/native runtime. No inherited commercial desktop publisher workflow or subscription lifecycle applies to this distribution.

Current platform acceptance: Studio marker create/readback/delete passed through the complete local SDK/runtime chain; Free marker acceptance also passed, while broader native behaviors remain pending. Windows startup deliberately rejects until private ACL validation and required local Free runtime prerequisites are implemented. DaVinci Resolve and third-party binaries are supplied by the user's installation, not this package.

Before changing an existing method contract, preserve explicit migration notes and compatibility tests. Source tests and simulated adapters are identified as such and never stand in for real native acceptance.
