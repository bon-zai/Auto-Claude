# Investigation: v2.7.1 Release Artifacts Issue

## Investigation Date

2025-12-25

## Summary

The v2.7.1 release has **incorrect files attached**. All artifacts have v2.7.0 in their filenames, indicating the wrong build artifacts were uploaded.

---

## Phase 1: Reproduce and Verify Issue

### Subtask 1-1: Current v2.7.1 Assets

**Command:** `gh release view v2.7.1 --json assets -q '.assets[].name'`

**Release Metadata:**
- Tag Name: v2.7.1
- Release Name: v2.7.1
- Published At: 2025-12-22T13:35:38Z
- Is Draft: false
- Is Prerelease: false

**Files Currently Attached to v2.7.1:**

| File Name | Size (bytes) | Expected Name |
|-----------|-------------|---------------|
| Auto-Claude-2.7.0-darwin-arm64.dmg | 124,187,073 | Auto-Claude-2.7.1-darwin-arm64.dmg |
| Auto-Claude-2.7.0-darwin-arm64.zip | 117,694,085 | Auto-Claude-2.7.1-darwin-arm64.zip |
| Auto-Claude-2.7.0-darwin-x64.dmg | 130,635,398 | Auto-Claude-2.7.1-darwin-x64.dmg |
| Auto-Claude-2.7.0-darwin-x64.zip | 124,176,354 | Auto-Claude-2.7.1-darwin-x64.zip |
| Auto-Claude-2.7.0-linux-amd64.deb | 104,558,694 | Auto-Claude-2.7.1-linux-amd64.deb |
| Auto-Claude-2.7.0-linux-x86_64.AppImage | 145,482,885 | Auto-Claude-2.7.1-linux-x86_64.AppImage |
| Auto-Claude-2.7.0-win32-x64.exe | 101,941,972 | Auto-Claude-2.7.1-win32-x64.exe |
| checksums.sha256 | 718 | checksums.sha256 (with v2.7.1 filenames) |

### Issue Confirmed

**Problem:** All 7 platform artifacts attached to v2.7.1 have "2.7.0" in their filename instead of "2.7.1".

**Impact:**
- Users downloading v2.7.1 are receiving v2.7.0 binaries
- File naming does not match the release version
- Checksums file likely references v2.7.0 filenames
- Auto-update mechanisms may be confused by version mismatch

**Evidence:**
```
Files attached to v2.7.1:
- Auto-Claude-2.7.0-darwin-arm64.dmg   (WRONG - should be 2.7.1)
- Auto-Claude-2.7.0-darwin-arm64.zip   (WRONG - should be 2.7.1)
- Auto-Claude-2.7.0-darwin-x64.dmg     (WRONG - should be 2.7.1)
- Auto-Claude-2.7.0-darwin-x64.zip     (WRONG - should be 2.7.1)
- Auto-Claude-2.7.0-linux-amd64.deb    (WRONG - should be 2.7.1)
- Auto-Claude-2.7.0-linux-x86_64.AppImage (WRONG - should be 2.7.1)
- Auto-Claude-2.7.0-win32-x64.exe      (WRONG - should be 2.7.1)
- checksums.sha256                      (likely references wrong filenames)
```

---

### Subtask 1-2: Comparison with v2.7.0 and Expected Naming

**Command:** `gh release view v2.7.0 --json assets -q '.assets[].name'`

#### v2.7.0 Release Analysis

**Release Metadata:**
- Tag Name: v2.7.0
- Release Name: v2.7.0
- Published At: 2025-12-22T13:19:13Z
- Target Commitish: main
- Is Draft: false
- Is Prerelease: false

**Critical Finding:** v2.7.0 has **NO assets attached** (empty assets array).

#### Release Timeline

| Release | Published At | Assets Count | Status |
|---------|-------------|--------------|--------|
| v2.7.0  | 2025-12-22T13:19:13Z | 0 | No files attached |
| v2.7.1  | 2025-12-22T13:35:38Z | 8 | Wrong version in filenames |
| v2.7.2  | 2025-12-22T13:52:51Z | ? | Draft release |

**Observation:** v2.7.0 was published 16 minutes before v2.7.1, but has no artifacts attached.

#### Checksums File Analysis

The `checksums.sha256` file attached to v2.7.1 contains:
```
0a0094ff3e52609665f6f0d6d54180dbfc592956f91ef2cdd94e43a61b6b24d2  ./Auto-Claude-2.7.0-darwin-arm64.dmg
43b168f3073d60644bb111c8fa548369431dc448e67700ed526cb4cad61034e0  ./Auto-Claude-2.7.0-darwin-arm64.zip
5150cbba934fbeb3d97309a493cc8ef3c035e9ec38b31f01382d628025f5c451  ./Auto-Claude-2.7.0-darwin-x64.dmg
ea9139277290a8189f799d00bc3cd1aaf81a16e890ff90327eca01a4cce73e61  ./Auto-Claude-2.7.0-darwin-x64.zip
078b2ba6a2594bf048932776dc31a45e59cd9cb23b34b2cf2f810f4101f04736  ./Auto-Claude-2.7.0-linux-amd64.deb
1feb6b9be348a5e23238e009dbc1ce8b2788103a262cd856613332b3ab1711e9  ./Auto-Claude-2.7.0-linux-x86_64.AppImage
25383314b3bc032ceaf8a8416d5383879ed351c906f03175b8533047647a612d  ./Auto-Claude-2.7.0-win32-x64.exe
```

**Issue:** Checksums file also references v2.7.0 filenames, confirming the build was run with v2.7.0 version.

#### Expected Naming Pattern (from release.yml)

Based on the release workflow analysis, artifacts follow this naming convention:
```
Auto-Claude-{version}-{platform}-{arch}.{ext}
```

Where version comes from `package.json` in `auto-claude-ui/`.

**Expected v2.7.1 Artifacts:**
| Expected Filename | Actual Filename (Wrong) |
|-------------------|-------------------------|
| Auto-Claude-2.7.1-darwin-arm64.dmg | Auto-Claude-2.7.0-darwin-arm64.dmg |
| Auto-Claude-2.7.1-darwin-arm64.zip | Auto-Claude-2.7.0-darwin-arm64.zip |
| Auto-Claude-2.7.1-darwin-x64.dmg | Auto-Claude-2.7.0-darwin-x64.dmg |
| Auto-Claude-2.7.1-darwin-x64.zip | Auto-Claude-2.7.0-darwin-x64.zip |
| Auto-Claude-2.7.1-linux-amd64.deb | Auto-Claude-2.7.0-linux-amd64.deb |
| Auto-Claude-2.7.1-linux-x86_64.AppImage | Auto-Claude-2.7.0-linux-x86_64.AppImage |
| Auto-Claude-2.7.1-win32-x64.exe | Auto-Claude-2.7.0-win32-x64.exe |
| checksums.sha256 (v2.7.1 refs) | checksums.sha256 (v2.7.0 refs) |

#### Hypothesis

The evidence suggests one of the following scenarios:

1. **Tag/Version Mismatch:** The v2.7.1 tag may point to a commit where `package.json` still had version `2.7.0`
2. **Workflow Re-run:** The v2.7.1 release may have been created by re-running the v2.7.0 workflow artifacts
3. **Manual Upload Error:** Artifacts from v2.7.0 were manually attached to the v2.7.1 release
4. **Artifact Caching:** Old workflow artifacts were incorrectly reused for v2.7.1

**Next step:** Check git tags and package.json versions to determine root cause.

---

### Subtask 1-3: Package.json Version and Git State Analysis

**Commands Used:**
- `git show v2.7.1:auto-claude-ui/package.json | jq -r '.version'`
- `git show v2.7.0:auto-claude-ui/package.json | jq -r '.version'`
- `git log --oneline v2.7.0..v2.7.1`
- `git rev-parse v2.7.1^{commit}`

#### Current Package.json State

| Location | Current Version |
|----------|-----------------|
| `auto-claude-ui/package.json` (HEAD) | 2.7.1 |

**Note:** The subtask referenced `apps/frontend/package.json`, but the actual path is `auto-claude-ui/package.json`.

#### Version at Git Tags

| Tag | Commit | package.json Version | Expected |
|-----|--------|---------------------|----------|
| v2.7.0 | `fe7290a8` | 2.6.5 | 2.7.0 |
| v2.7.1 | `772a5006` | **2.7.0** ❌ | 2.7.1 |

#### Commit Timeline

```
fc2075dd auto-claude: subtask-1-2 - Compare v2.7.1 artifacts...
ff033a8e auto-claude: subtask-1-1 - List all files...
8db71f3d Update version to 2.7.1 in package.json    <-- Version bump (AFTER tag)
772a5006 2.7.1                                      <-- v2.7.1 TAG placed here
d23fcd86 Enhance VirusTotal scan error handling...
...more commits...
fe7290a8 Release v2.7.0...                          <-- v2.7.0 TAG placed here
```

#### Root Cause Identified ✅

**Problem:** The `v2.7.1` tag was placed on commit `772a5006` BEFORE the `package.json` version was updated to `2.7.1`.

**Timeline of error:**
1. Commit `772a5006` created with message "2.7.1" - tag `v2.7.1` placed here
2. At this commit, `package.json` still contained version `2.7.0`
3. The release workflow triggered on tag push, building with version `2.7.0` from `package.json`
4. All artifacts named with `2.7.0` because that's what was in `package.json`
5. Commit `8db71f3d` later updated `package.json` to `2.7.1` (but tag was already pushed)

**This is a "tag before version bump" error.**

The release workflow correctly read the version from `package.json`, but the tag was created before the version was bumped. The naming convention `${productName}-${version}-${platform}-${arch}.${ext}` correctly used version `2.7.0` because that's what was in `package.json` at the tagged commit.

#### Verification of Build Configuration

From `auto-claude-ui/package.json`:
```json
"build": {
  "artifactName": "${productName}-${version}-${platform}-${arch}.${ext}",
  ...
}
```

This confirms the version is sourced from `package.json` during the build process.

#### Git State Summary

| Metric | Value |
|--------|-------|
| Current Branch | `auto-claude/009-latest-release-v2-7-1-has-wrong-files-attached` |
| Working Tree | Clean |
| Current HEAD package.json | 2.7.1 |
| v2.7.1 tag package.json | 2.7.0 ❌ |
| v2.7.0 tag package.json | 2.6.5 ❌ |

**Note:** Both v2.7.0 and v2.7.1 tags have version mismatches in `package.json`, indicating a pattern of tagging before version bumping.

---

## Root Cause Summary

| Factor | Finding |
|--------|---------|
| What happened? | v2.7.1 tag placed before package.json version bump |
| Why? | Incorrect release process: tag first, version bump second |
| Impact | All 7 artifacts have v2.7.0 in filename |
| Evidence | `git show v2.7.1:auto-claude-ui/package.json` shows version 2.7.0 |

---

## Phase 2: Root Cause Analysis

### Subtask 2-1: Inspect v2.7.1 Git Tag and Commit

**Commands Used:**
```bash
git log -1 v2.7.1 --format='%H %s %ci'
git show v2.7.1 --format='Commit: %H%nAuthor: %an <%ae>%nDate: %ci%nMessage: %s' --no-patch
git tag -l v2.7.1 -n1
git cat-file -t v2.7.1
git show v2.7.1:auto-claude-ui/package.json | head -10 | grep version
```

#### Tag Details

| Property | Value |
|----------|-------|
| Tag Name | v2.7.1 |
| Tag Type | Lightweight (commit reference, not annotated) |
| Points To | `772a5006d45487b600ce4079bae1c98f9ccf6b2e` |

#### Tagged Commit Details

| Property | Value |
|----------|-------|
| Commit Hash | `772a5006d45487b600ce4079bae1c98f9ccf6b2e` |
| Author | AndyMik90 <andre@mikalsenutvikling.no> |
| Commit Date | 2025-12-22 14:35:30 +0100 |
| Commit Message | `2.7.1` |
| package.json Version | **2.7.0** (MISMATCH) |

#### Verification Output

```
$ git log -1 v2.7.1 --format='%H %s %ci'
772a5006d45487b600ce4079bae1c98f9ccf6b2e 2.7.1 2025-12-22 14:35:30 +0100

$ git show v2.7.1:auto-claude-ui/package.json | grep version
  "version": "2.7.0",
```

#### Commit Context

```
$ git log -3 --oneline v2.7.1
772a5006 2.7.1                                        <-- v2.7.1 TAG HERE
d23fcd86 Enhance VirusTotal scan error handling...
326118bd Refactor macOS build workflow...
```

#### Analysis

1. **Tag Type:** The tag is a lightweight tag (just a commit reference), not an annotated tag. This means there's no separate tag object with metadata, author, or message.

2. **Commit Message vs Version:** The commit message says "2.7.1" but the `package.json` at this commit still contains version `2.7.0`. This is the source of the mismatch.

3. **Release Workflow Behavior:** When the GitHub release workflow triggered on tag push `v2.7.1`:
   - It checked out commit `772a5006`
   - It read version from `auto-claude-ui/package.json` which was `2.7.0`
   - It built artifacts with `2.7.0` in the filename
   - It uploaded these incorrectly-versioned artifacts to the v2.7.1 release

4. **Timeline Confirmation:**
   - Tag created: 2025-12-22 14:35:30 +0100
   - Release published: 2025-12-22T13:35:38Z (same time, UTC)
   - Version bump commit `8db71f3d` happened AFTER this

#### Root Cause Confirmed

The v2.7.1 tag points to a commit where `package.json` still had version `2.7.0`. This is a **"tag before version bump"** error in the release process.

The correct sequence should have been:
1. First: Bump package.json version to 2.7.1
2. Second: Commit the version bump
3. Third: Create and push the v2.7.1 tag

What actually happened:
1. Created tag v2.7.1 on commit with package.json version 2.7.0
2. Workflow triggered and built with wrong version
3. Version bump to 2.7.1 committed afterwards (too late)

---

### Subtask 2-2: GitHub Actions Workflow Run Analysis

**Commands Used:**
```bash
gh run list --workflow=release.yml --limit=20
gh run view 20433472030 --json conclusion,status,headSha,event,jobs
gh run view 20433472034 --json conclusion,status,headSha,jobs  # Validate Version workflow
```

#### Release Workflow Run Details

| Property | Value |
|----------|-------|
| Run ID | 20433472030 |
| Status | Completed |
| Conclusion | **success** |
| Event | push (tag v2.7.1) |
| Head SHA | `772a5006d45487b600ce4079bae1c98f9ccf6b2e` |
| Created At | 2025-12-22T13:35:39Z |
| Updated At | 2025-12-22T13:53:02Z |
| Total Duration | ~17 minutes |

#### Build Jobs Summary

| Job | Status | Duration | Started | Completed |
|-----|--------|----------|---------|-----------|
| build-linux | ✅ success | ~2.5 min | 13:35:42Z | 13:38:15Z |
| build-windows | ✅ success | ~4.5 min | 13:35:41Z | 13:40:11Z |
| build-macos-intel | ✅ success | ~7 min | 13:35:42Z | 13:42:52Z |
| build-macos-arm64 | ✅ success | ~5.5 min | 13:35:42Z | 13:41:12Z |
| create-release | ✅ success | ~10 min | 13:42:55Z | 13:53:01Z |

#### Create-Release Job Steps

| Step | Conclusion |
|------|------------|
| Set up job | ✅ success |
| Run actions/checkout@v4 | ✅ success |
| Download all artifacts | ✅ success |
| Flatten and validate artifacts | ✅ success |
| Generate checksums | ✅ success |
| Scan with VirusTotal | ✅ success |
| Dry run summary | ⏭️ skipped |
| Generate changelog | ✅ success |
| Create Release | ✅ success |

**Workflow Analysis:** The release workflow executed **successfully** - all build jobs and the release creation completed without errors. The workflow correctly:
1. Checked out commit `772a5006d45487b600ce4079bae1c98f9ccf6b2e`
2. Built artifacts for all platforms (Linux, Windows, macOS Intel, macOS ARM64)
3. Generated checksums
4. Ran VirusTotal scans
5. Created the GitHub release with artifacts

**Key Finding:** The workflow operated as designed. The problem was the **input** (source code at tagged commit), not the **workflow logic**.

---

#### 🚨 CRITICAL: Validate Version Workflow FAILED

**Run ID:** 20433472034
**Conclusion:** ❌ **FAILURE**

| Step | Conclusion |
|------|------------|
| Set up job | ✅ success |
| Checkout | ✅ success |
| Extract version from tag | ✅ success |
| Extract version from package.json | ✅ success |
| **Compare versions** | ❌ **FAILURE** |
| Version validation result | ⏭️ skipped |

**What Happened:**
1. The `validate-version.yml` workflow triggered on the v2.7.1 tag push
2. It correctly detected that:
   - Tag version: `2.7.1`
   - package.json version: `2.7.0`
3. It **FAILED** with an error because versions didn't match

**Why Didn't This Stop the Release?**

The `validate-version.yml` and `release.yml` workflows are **independent**:
- Both trigger on `push: tags: - 'v*'`
- They run in **parallel**, not sequentially
- The release workflow has **no dependency** on the validation workflow
- Even though validation failed, the release proceeded and succeeded

**Validation Workflow (from `.github/workflows/validate-version.yml`):**
```yaml
on:
  push:
    tags:
      - 'v*'
```

**Expected Output from Failed Validation:**
```
❌ ERROR: Version mismatch detected!

The version in package.json (2.7.0) does not match
the git tag version (2.7.1).

To fix this:
  1. Delete this tag: git tag -d v2.7.1
  2. Update package.json version to 2.7.1
  3. Commit the change
  4. Recreate the tag: git tag -a v2.7.1 -m 'Release v2.7.1'
```

---

#### Workflow Architecture Issue

```
Tag Push (v2.7.1)
       │
       ├──────────────────────────────────┐
       │                                  │
       ▼                                  ▼
┌──────────────────┐            ┌──────────────────┐
│  validate-version │            │     release      │
│    ❌ FAILED      │            │   ✅ SUCCESS     │
│ (detected error)  │  ← No    │  (built wrong     │
│                   │   link →  │   version)        │
└──────────────────┘            └──────────────────┘
```

**Problem:** The validation workflow runs but cannot **block** the release workflow.

---

#### Other v2.7.1 Workflows

| Workflow | Run ID | Conclusion | Notes |
|----------|--------|------------|-------|
| Release | 20433472030 | ✅ success | Built and released v2.7.0 files |
| Validate Version | 20433472034 | ❌ failure | Detected mismatch but couldn't stop release |
| Discord Release Notification | 20433472029 | ✅ success | Notified Discord about "v2.7.1" |
| Test on Tag | 20433472046 | ✅ success | Tests passed |
| Build Native Module Prebuilds | 20433472017 | ❌ failure | Separate prebuilt module issue |

---

#### Root Cause Confirmation

The GitHub Actions analysis confirms:

1. **The release workflow worked correctly** - it built exactly what was in the source code at the tagged commit
2. **The validation workflow detected the problem** - it correctly identified the version mismatch
3. **The workflows are not connected** - validation failure could not prevent the release
4. **The artifacts are from the right commit but wrong version** - v2.7.1 release contains v2.7.0 artifacts because that's what package.json said at commit `772a5006`

---

## Next Steps

1. ~~**Subtask 1-1:** Verify v2.7.1 assets~~ ✅ Complete
2. ~~**Subtask 1-2:** Compare with v2.7.0 release and verify expected naming pattern~~ ✅ Complete
3. ~~**Subtask 1-3:** Check package.json version and git state~~ ✅ Complete - ROOT CAUSE IDENTIFIED
4. ~~**Subtask 2-1:** Inspect v2.7.1 git tag and commit~~ ✅ Complete - TAG/COMMIT MISMATCH CONFIRMED
5. ~~**Subtask 2-2:** Check release workflow runs~~ ✅ Complete - VALIDATION DETECTED BUT COULDN'T STOP RELEASE
6. **Subtask 2-3:** Document fix options
7. **Phase 3:** Implement fix (re-upload correct files or publish v2.7.2)
8. **Phase 4:** Add validation to prevent future occurrences

---

## Status: Phase 2 In Progress - Subtask 2-2 Complete

**Root Cause:** The v2.7.1 tag was created on commit `772a5006` which still had `package.json` version `2.7.0`. The validation workflow detected this but couldn't stop the release workflow.

**Key Findings from Workflow Analysis:**
- Release workflow (ID: 20433472030): ✅ Success - correctly built from tagged commit
- Validate Version workflow (ID: 20433472034): ❌ Failed - correctly detected version mismatch
- The workflows run in parallel with no dependency relationship

**Recommended Fix:**
1. Delete the v2.7.1 tag and release
2. Move the tag to a commit where package.json has version 2.7.1
3. Re-trigger the release workflow, OR
4. Mark v2.7.1 as deprecated and release v2.7.2 with correct versioning

**Process Improvement Needed:**
- Version bump should ALWAYS happen BEFORE tagging
- **Make release.yml depend on validate-version.yml** using `needs:` or combine them
- Consider using a reusable workflow or job dependency to enforce validation
