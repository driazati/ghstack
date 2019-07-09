#!/usr/bin/env python3

from dataclasses import dataclass
from ghstack.typing import GitHubNumber, GitTreeHash
import ghstack.shell
from typing import Optional
import re
from abc import ABCMeta, abstractmethod


RE_GH_METADATA = re.compile(
    r'gh-metadata: (?P<owner>[^/]+) (?P<repo>[^/]+) (?P<number>[0-9]+) '
    r'gh/(?P<username>[a-zA-Z0-9-]+)/(?P<ghnum>[0-9]+)/head', re.MULTILINE)


RE_PULL_REQUEST_RESOLVED = re.compile(
    r'Pull Request resolved: '
    r'https://github.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>[0-9]+)'
)


@dataclass
class PullRequestResolved:
    owner: str
    repo: str
    number: GitHubNumber

    @staticmethod
    def search(s: str) -> Optional['PullRequestResolved']:
        m = RE_PULL_REQUEST_RESOLVED.search(s)
        if m is not None:
            return PullRequestResolved(
                owner=m.group("owner"),
                repo=m.group("repo"),
                number=GitHubNumber(int(m.group("number"))),
            )
        m = RE_GH_METADATA.search(s)
        if m is not None:
            return PullRequestResolved(
                owner=m.group("owner"),
                repo=m.group("repo"),
                number=GitHubNumber(int(m.group("number"))),
            )
        return None


class Patch(metaclass=ABCMeta):
    """
    Abstract representation of a patch, i.e., some actual
    change between two trees.
    """
    @abstractmethod
    def apply(self, sh: ghstack.shell.Shell, h: GitTreeHash) -> GitTreeHash:
        pass


@dataclass
class Diff:
    """
    An abstract representation of a diff.  Diffs can come from
    git or hg.
    """
    # Title of the diff
    title: str

    # Detailed description of the diff.  Includes the title.
    summary: str

    # Unique identifier representing the commit in question (may be a
    # Git/Mercurial commit hash; the important thing is that it can be
    # used as a unique identifier.)
    oid: str

    # Unique identifier representing the commit in question, but it
    # is *invariant* to changes in commit message / summary.  In Git,
    # a valid identifier would be the tree hash of the commit (rather
    # than the commit hash itself); in Phabricator it could be the
    # version of the diff.
    source_id: str

    # The contents of 'Pull Request resolved'.  This is None for
    # diffs that haven't been submitted by ghstack.  For BC reasons,
    # this also accepts gh-metadata.
    pull_request_resolved: Optional[PullRequestResolved]

    # Function which applies this diff to the input tree, producing a
    # new tree.  There will only be two implementations of this:
    #
    #   - Git: A no-op function, which asserts that GitTreeHash is some
    #     known tree and then returns a fixed GitTreeHash (since we
    #     already know exactly what tree we want.)
    #
    #   - Hg: A function which applies some patch to the git tree
    #     giving you the result.
    #
    # This function is provided a shell whose cwd is the Git repository
    # that the tree hashes live in.
    #
    # NB: I could have alternately represented this as
    # Optional[GitTreeHash] + Optional[UnifiedDiff] but that would
    # require me to read out diff into memory and I don't really want
    # to do that if I don't have to.
    patch: Patch
