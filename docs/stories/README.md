# Development Stories - Reddit MCP Server

**Purpose:** This directory contains development epics and user stories for the Reddit MCP Server project.

---

## Directory Structure

```
stories/
├── README.md                      # This file (story management guide)
├── epic-01-mvp-foundation.md      # Week 1-2: MVP Development
├── epic-02-monetization.md        # Week 3-4: v1.0 Launch (TBD)
└── epic-03-enterprise.md          # Week 5-8: v2.0 Features (TBD)
```

---

## Epic/Story Structure

### What is an Epic?

An epic is a large body of work that can be broken down into multiple user stories. Each epic represents a significant milestone (e.g., MVP, v1.0 launch, enterprise features).

**Epic Structure:**
- Epic ID: EPIC-XX
- Timeline: Week range
- Goal: High-level objective
- Stories: 5-15 stories
- Success Criteria: Measurable outcomes

### What is a Story?

A story is a small, deliverable unit of work (1-2 days max). Each story follows this template:

```markdown
## Story X: [Title]

**Story ID:** MVP-XXX
**Priority:** P0/P1/P2
**Estimated Effort:** S (2-3h) / M (4-6h) / L (6-8h)

### User Story
As a [persona], I want [goal] so that [benefit].

### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Technical Notes
- Reference: [doc link]
- Key implementation details

### Definition of Done
- [ ] Code complete
- [ ] Tests passing
- [ ] Documented

### Dependencies
- Story IDs that must be completed first
```

---

## Story States

### State Definitions

1. **Backlog**: Story written but not started
2. **In Progress**: Developer actively working on story
3. **Code Review**: Code complete, awaiting review
4. **Testing**: In QA/testing phase
5. **Done**: All acceptance criteria met, Definition of Done complete
6. **Blocked**: Cannot proceed due to dependency/issue

### How to Mark Stories as Done

When completing a story:

1. **Check all boxes** in Acceptance Criteria and Definition of Done
2. **Update story header** with completion date:
   ```markdown
   **Status:** Done ✅
   **Completed:** 2025-11-10
   ```
3. **Add completion notes** at bottom:
   ```markdown
   ---
   ## Completion Notes
   - Actual effort: 5 hours
   - Issues encountered: Redis connection timeout in tests (fixed)
   - Lessons learned: Cache key generation needed more thorough testing
   ```
4. **Update Epic Metrics** in epic file (velocity tracking)

---

## Sprint Planning

### Week 1-2: MVP Sprint

**Goal:** Complete EPIC-01 (10 stories)

**Sprint Breakdown:**

#### Week 1 (Days 1-5)
- **Day 1**: MVP-001 (Project Setup)
- **Day 2**: MVP-002 (Redis Caching) + MVP-003 (Reddit Client)
- **Day 3**: MVP-004 (Rate Limiter) + MVP-005 (FastMCP Server)
- **Day 4**: MVP-006 (search_reddit)
- **Day 5**: MVP-007 (get_subreddit_posts)

#### Week 2 (Days 6-10)
- **Day 6**: MVP-008 (get_post_comments)
- **Day 7**: MVP-009 (get_trending_topics)
- **Day 8-9**: MVP-010 (Testing & Documentation)
- **Day 10**: Buffer/polish/beta testing

**Daily Standup Questions:**
1. What did I complete yesterday?
2. What am I working on today?
3. Any blockers?

---

## Story Template (For New Stories)

Use this template when creating new stories in future epics:

```markdown
## Story X: [Title]

**Story ID:** [EPIC]-XXX
**Priority:** P0 (Must Have) / P1 (Should Have) / P2 (Nice to Have)
**Estimated Effort:** S (2-3h) / M (4-6h) / L (6-8h) / XL (8-16h)

### User Story
As a [user type]
I want [goal]
So that [benefit/reason]

### Acceptance Criteria
- [ ] Functional requirement 1
- [ ] Functional requirement 2
- [ ] Performance requirement (if applicable)
- [ ] Error handling requirement

### Technical Notes
- **Reference Documents:** [Link to architecture/spec docs]
- **Key Technologies:** [Libraries/frameworks used]
- **Implementation Approach:** [Brief technical approach]
- **Potential Gotchas:** [Known challenges]

### Definition of Done
- [ ] Code implemented and follows coding-standards.md
- [ ] Unit tests written (>80% coverage)
- [ ] Integration tests written (if applicable)
- [ ] Type checking passes (mypy --strict)
- [ ] Linting passes (Black, Ruff)
- [ ] Code reviewed by [reviewer]
- [ ] Documentation updated (if public API)
- [ ] Deployed to test environment
- [ ] Acceptance criteria verified

### Dependencies
- [STORY-ID]: [Reason why this is needed first]

### Test Scenarios
1. **Happy Path:** [Description]
2. **Edge Case 1:** [Description]
3. **Error Scenario:** [Description]

---
## Completion Notes
*(Fill after completion)*
- **Completed:** [Date]
- **Actual Effort:** [Hours]
- **Issues Encountered:** [List]
- **Lessons Learned:** [List]
```

---

## Story Estimation Guidelines

### Effort Levels

| Size | Hours | When to Use |
|------|-------|-------------|
| S (Small) | 2-3h | Simple, clear implementation. No unknowns. |
| M (Medium) | 4-6h | Moderate complexity. Some research needed. |
| L (Large) | 6-8h | Complex feature. Multiple components. Testing time. |
| XL (Extra Large) | 8-16h | Should be split into smaller stories. Avoid if possible. |

### Estimation Factors
- Implementation complexity
- Testing time (unit + integration)
- Documentation time
- Unknown/research time
- Integration with other components

**Rule of Thumb:** If a story is >8 hours, split it into multiple stories.

---

## Working with Dependencies

### Story Dependencies

Some stories must be completed before others can start:

**Example:**
- MVP-006 (search_reddit) depends on MVP-002 (caching), MVP-003 (Reddit client), MVP-004 (rate limiter)

### How to Handle Blocked Stories

If a story is blocked:

1. **Mark as Blocked:**
   ```markdown
   **Status:** Blocked ⚠️
   **Blocked By:** MVP-002 (Redis caching not complete)
   **Blocked Since:** 2025-11-08
   ```

2. **Work on non-dependent story** from sprint backlog

3. **Communicate in standup:** "MVP-006 is blocked by MVP-002, working on MVP-005 instead"

4. **Unblock when dependency resolves:**
   ```markdown
   **Status:** In Progress 🚧
   **Unblocked:** 2025-11-09
   ```

---

## Quality Gates

Before marking any story as "Done", verify:

### Code Quality
- [ ] All acceptance criteria checked
- [ ] Type hints on all functions
- [ ] Docstrings on public functions
- [ ] No linting errors (Ruff)
- [ ] No type errors (mypy --strict)
- [ ] Code formatted (Black)

### Testing
- [ ] Unit tests written and passing
- [ ] Integration tests written (if needed)
- [ ] Test coverage >80% on new code
- [ ] Edge cases covered
- [ ] Error scenarios tested

### Documentation
- [ ] Public APIs documented
- [ ] Complex logic has inline comments
- [ ] README updated (if needed)
- [ ] Architecture docs updated (if design changed)

### Deployment
- [ ] Builds successfully (docker build)
- [ ] Runs in local environment
- [ ] Environment variables documented (if new)

**Golden Rule:** If you wouldn't be comfortable handing this to another developer to maintain, it's not done.

---

## Epic Completion Checklist

When all stories in an epic are done:

### Epic Review
- [ ] All stories in "Done" state
- [ ] Epic success criteria met
- [ ] No P0/P1 bugs remaining
- [ ] Performance targets achieved
- [ ] Documentation complete
- [ ] Deployment successful

### Retrospective
- [ ] "What went well?" documented
- [ ] "What could be improved?" documented
- [ ] Action items for next epic created

### Handoff
- [ ] Demo recorded (if applicable)
- [ ] Beta users notified (if applicable)
- [ ] Next epic planning scheduled

---

## Tools & Workflow

### Recommended Workflow

1. **Daily:**
   - Review today's story
   - Update story status
   - Check dependencies
   - Standup (3 questions)

2. **Per Story:**
   - Read story fully before starting
   - Check technical notes and references
   - Implement feature
   - Write tests
   - Check all acceptance criteria
   - Mark as done with notes

3. **End of Week:**
   - Update epic velocity
   - Review blockers
   - Plan next week's stories

### GitHub Integration (Optional)

For teams using GitHub Issues:

1. Create Issue for each story (copy story template)
2. Label with priority (P0/P1/P2) and size (S/M/L)
3. Link to epic with "Part of EPIC-01" in description
4. Use GitHub Projects for kanban board
5. Close issue when story done

---

## FAQ

### Q: What if a story takes longer than estimated?

**A:** Update the story with actual effort in completion notes. This helps improve future estimates. If significantly over (2x), consider if story was too large.

### Q: Can I work on multiple stories simultaneously?

**A:** Not recommended. Focus on one story at a time to maintain quality and reduce context switching. Exception: If blocked, work on next unblocked story.

### Q: What if requirements change mid-story?

**A:** Document change in story notes. If change is minor, proceed. If major (>2 hours impact), pause story and discuss with PM/tech lead.

### Q: How do I handle discovered bugs?

**A:**
- **Blocker bugs (P0):** Create immediate story, prioritize over current work
- **Major bugs (P1):** Add to current sprint
- **Minor bugs (P2):** Add to backlog for future sprint

### Q: Can I skip writing tests?

**A:** No. Tests are part of Definition of Done. No story is complete without tests. If short on time, reduce scope, don't skip tests.

---

## Story Management Best Practices

### DO:
✅ Keep stories small (1-2 days max)
✅ Write clear acceptance criteria (testable)
✅ Update story status daily
✅ Document completion notes
✅ Test before marking done
✅ Check all dependencies before starting

### DON'T:
❌ Start stories with incomplete dependencies
❌ Skip Definition of Done items
❌ Create stories without acceptance criteria
❌ Leave stories in "In Progress" for >3 days
❌ Work on stories outside current sprint (unless urgent)

---

## References

- **PRD:** `/Users/padak/github/apify-actors/docs/prd/prd.md`
- **Architecture:** `/Users/padak/github/apify-actors/docs/system-architecture.md`
- **Feature Specs:** `/Users/padak/github/apify-actors/docs/feature-specifications.md`
- **Coding Standards:** `/Users/padak/github/apify-actors/docs/architecture/coding-standards.md`
- **Source Tree:** `/Users/padak/github/apify-actors/docs/architecture/source-tree.md`

---

**Questions?** Contact project tech lead or PM.

**Last Updated:** 2025-11-05
