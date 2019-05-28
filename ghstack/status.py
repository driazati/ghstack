#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ghstack.github
import ghstack.circleci
import ghstack.github_utils
from ghstack.typed_dict import TypedDict

import asyncio
import re
import logging

RE_CIRCLECI_URL = re.compile(r'^https://circleci.com/gh/pytorch/pytorch/([0-9]+)')


async def main(pull_request: str,
         github: ghstack.github.GitHubEndpoint,
         circleci: ghstack.circleci.CircleCIEndpoint) -> None:

    # Game plan:
    # 1. Query GitHub to find out what the current statuses are
    #       (TODO: if we got rate limited we'll miss stuff)
    # 2. For each status in parallel:
    #   a. Query CircleCI for job status
    #   b. (Future work) Query output_url to get log information
    #      (it's gzip'ed)
    #
    # For now:
    #   - Print if the job actually ran, or was skipped
    #       - Easy way to determine: check if "Should run job after
    #         checkout" is last step
    #       - I inspected circleci.get('project/github/pytorch/pytorch/1773555')
    #         to see if there were other options, there did not appear
    #         to be any indication that a halt was called.  So we'll
    #         have to rely on the (OS X jobs, take note!)

    params = ghstack.github_utils.parse_pull_request(pull_request)

    ContextPayload = TypedDict("ContextPayload", {
        "context": str,
        "state": str,
        "targetUrl": str,
    })
    r = github.graphql("""
    query ($name: String!, $owner: String!, $number: Int!) {
        repository(name: $name, owner: $owner) {
            pullRequest(number: $number) {
                commits(last: 1) {
                    nodes {
                        commit {
                            status {
                                contexts {
                                    context
                                    state
                                    targetUrl
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """, **params)
    contexts = r['data']['repository']['pullRequest']['commits']['nodes'][0]['commit']['status']['contexts']

    async def process_context(context: ContextPayload) -> str:
        if 'circleci' in context['context']:
            m = RE_CIRCLECI_URL.match(context['targetUrl'])
            if not m:
                logging.warning("Malformed CircleCI URL {}".format(context['targetUrl']))
                return "INTERNAL ERROR {}".format(context['context'])
            buildid = m.group(1)
            if context['state'] not in {'SUCCESS', 'PENDING'}:
                state = context['state']
            else:
                r = await circleci.get("project/github/{name}/{owner}/{buildid}".format(buildid=buildid, **params))
                if r["failed"]:
                    state = "FAILED"
                elif r["canceled"]:
                    state = "CANCELED"
                elif "Should Run Job" in r["steps"][-1]["name"]:
                    state = "SKIPPED"
                else:
                    state = "SUCCESS"
        else:
            state = context['state']

        if state == "SUCCESS":
            state = "✅"
        elif state == "SKIPPED":
            state = "❔"
        elif state == "CANCELED":
            state = "💜"
        elif state == "PENDING":
            state = "🚸"
        elif state == "FAILURE":
            state = "❌"
        name = context['context']
        url = context["targetUrl"]
        url = url.replace("?utm_campaign=vcs-integration-link&utm_medium=referral&utm_source=github-build-link", "")
        return "{} {} {}".format(state, name.ljust(70), url)

    results = await asyncio.gather(*[asyncio.ensure_future(process_context(c)) for c in contexts])
    print("\n".join(sorted(results)))
