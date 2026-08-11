# 管理员物理删除 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Admin-only hard delete for any status RSP record with confirm-only UX.

**Architecture:** Mirror void/reopen: `can_delete` → `service.delete` → storage cascade delete in one transaction → DELETE API → ledger「删除」action.

**Tech Stack:** Existing module Python/JS/static tests.

### Task 1: Backend permission + storage + service + API
### Task 2: Frontend api/ledger/table
### Task 3: Docs/manifest/tests
