from __future__ import annotations

from . import greenhouse_apply, lever_apply, github_apply

APPLY_FNS = {
    "greenhouse": greenhouse_apply.apply,
    "lever": lever_apply.apply,
    "github": github_apply.apply,
}
