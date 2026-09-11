# CutAgent SDK lifecycle

Public source preview: https://github.com/jindratilk/davinci-resolve-sdk. The local package remains private:true to prevent accidental npm publication. Registry distribution is not activated.

The complete inherited API and explicit subpaths are preserved at the 0.2.0 authoring baseline. Internal compatibility fields retain their historical names; the active distribution is `standalone_local`. Runtime negotiation still validates protocol, source identity and compatible version ranges.

A release requires standalone Free acceptance, an exact reviewed source/package inventory, reproducible source builds, dependency license notices and a deliberate public repository/package release decision. The root npm tarball includes the client and companion Python/native runtime source. Local editing works without an account or subscription.

Historical platform baselines: Studio marker create/readback/delete passed at commit fb4ad93 and the Free marker flow passed at commit 172232a. Those retained records do not qualify the current candidate head. Current-candidate Studio revalidation awaits the exclusive native lane, current-candidate Free revalidation awaits the remote handoff, and broader native behaviors remain pending. Windows is explicitly deferred and startup deliberately rejects until private ACL validation and required local Free runtime prerequisites are implemented. DaVinci Resolve and third-party binaries are supplied by the user's installation, not this package.

Before changing an existing method contract, preserve explicit migration notes and compatibility tests. Source tests and simulated adapters are identified as such and never stand in for real native acceptance.

## Copying managed artifacts

`artifact.copyTo(absolutePath)` never overwrites an existing destination. Managed and render artifacts download into a private temporary file beside the destination, verify the file's size and SHA-256, and then publish it with an exclusive hard link. A file created by another process during the download is preserved and publication fails. Existing destinations are rejected before downloading.

When the filesystem explicitly reports that hard links are unsupported (`ENOTSUP`, `EOPNOTSUPP` or `ENOSYS`), the SDK exclusively creates the destination and copies the already verified local content through its open descriptor. This fallback is visible while copying and may leave an incomplete new destination if copying fails. Inspect that file before removing it or retry with a new destination. Permission errors, cross-device errors and existing files do not trigger the fallback; support for every removable or network filesystem is not implied.

Error cleanup only removes private staging files. It never deletes the caller's destination pathname, which another process may have replaced. Successful publication verifies that the destination still identifies the verified file. An unavailable file identity or a replaced destination fails verification.
