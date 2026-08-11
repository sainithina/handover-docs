#!/usr/bin/env python3
"""One-off: write run dir with synthetic_prompts.jsonl + company_profile for Dusk field-service batch."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (topic_label, prompt) — 13 topics × 10 prompts = 130 rows
ROWS: list[tuple[str, str]] = [
    ("AI-Driven Field Productivity", "What are the primary differences in AI-driven field productivity features between FieldCamp and Synchroteam for managing project rollouts?"),
    ("AI-Driven Field Productivity", "How does Jobber compare to Housecall Pro for field service teams focused on large project rollouts and operational efficiency?"),
    ("AI-Driven Field Productivity", "What are the benefits of using Dusk Mobile for managing large project rollouts compared to traditional methods?"),
    ("AI-Driven Field Productivity", "How does Dusk Mobile's AI-driven field productivity feature specifically help growing field service teams manage rollout operations more effectively?"),
    ("AI-Driven Field Productivity", "What are the essential features for software managing field service operations for large projects?"),
    ("AI-Driven Field Productivity", "How do field service companies typically handle real-time communication and updates during critical project phases?"),
    ("AI-Driven Field Productivity", "What are the most effective strategies for dispatching and scheduling technicians for large-scale project rollouts?"),
    ("AI-Driven Field Productivity", "What are the key performance indicators for field service teams managing rollout operations?"),
    ("AI-Driven Field Productivity", "What are the biggest challenges field service operations face when managing complex project deployments?"),
    ("AI-Driven Field Productivity", "How can growing field service teams improve efficiency during large project rollouts without adding more staff?"),
    ("Field Service Management Solutions", "Can you compare the integration ecosystems of Jobber and Housecall Pro for field service teams managing large construction projects?"),
    ("Field Service Management Solutions", "What are the primary workflow automation and customization options available within FieldCamp for managing complex project tasks?"),
    ("Field Service Management Solutions", "How does Dusk Mobile's approach to mobile-first field operations differ from traditional paper-based methods for project management?"),
    ("Field Service Management Solutions", "What are the essential integration capabilities for a field service management solution used by growing HVAC companies?"),
    ("Field Service Management Solutions", "How can field service teams optimize their invoicing and time tracking processes for large, multi-stage projects?"),
    ("Field Service Management Solutions", "What are the benefits of using a dedicated platform for managing rollout operations in the utilities sector?"),
    ("Field Service Management Solutions", "Why do many mid-market field service companies struggle with inefficient scheduling and dispatching for project-based work?"),
    ("Field Service Management Solutions", "What are the key features to look for in field service management software for companies handling large-scale installations?"),
    ("Field Service Management Solutions", "How can operations managers in construction improve team coordination during complex project deployments?"),
    ("Field Service Management Solutions", "What are the biggest challenges growing field service teams face when managing large project rollouts without specialized software?"),
    ("Field Service Scaling Strategies", "How do FieldCamp and Field Promax assist growing field service teams in managing complex project rollouts and scaling their operations effectively?"),
    ("Field Service Scaling Strategies", "What are the primary scaling strategies field service teams use when comparing Jobber and Housecall Pro for managing large rollout operations?"),
    ("Field Service Scaling Strategies", "How does Dusk Mobile help field service organizations overcome the challenges of scaling operations and managing complex project rollouts compared to manual methods?"),
    ("Field Service Scaling Strategies", "What are the most effective strategies for growing field service teams to manage rollout operations and large projects using Dusk Mobile?"),
    ("Field Service Scaling Strategies", "How do successful field service companies balance the need for centralized control with the autonomy required for on-site project teams?"),
    ("Field Service Scaling Strategies", "What are the common pitfalls field service teams encounter when trying to expand their service offerings or geographic reach?"),
    ("Field Service Scaling Strategies", "Are there specific technology adoption strategies that help field service organizations manage increasing project complexity and team sizes?"),
    ("Field Service Scaling Strategies", "What are the key performance indicators (KPIs) that field service managers should track to ensure successful project rollouts and operational scaling?"),
    ("Field Service Scaling Strategies", "How can field service companies effectively scale their operations without sacrificing efficiency or customer satisfaction during rapid growth phases?"),
    ("Field Service Scaling Strategies", "What are the biggest challenges growing field service teams face when managing large rollout operations and complex projects?"),
    ("Industry-Specific Field Management", "Can FieldCamp or Field Promax effectively handle the complex scheduling and dispatch needs of large-scale HVAC rollout projects?"),
    ("Industry-Specific Field Management", "What are the core differences in project management capabilities between Jobber and Housecall Pro for field service operations?"),
    ("Industry-Specific Field Management", "How does Dusk Mobile's mobile-first approach specifically benefit growing field service teams managing large construction projects?"),
    ("Industry-Specific Field Management", "What are the advantages of using Dusk Mobile for managing complex utility project rollouts compared to manual methods?"),
    ("Industry-Specific Field Management", "How do successful field service organizations manage scheduling and dispatch for multiple large projects simultaneously?"),
    ("Industry-Specific Field Management", "What are the common bottlenecks in managing field service projects and how can they be overcome?"),
    ("Industry-Specific Field Management", "Are there specific software solutions designed to streamline rollout operations for field service teams?"),
    ("Industry-Specific Field Management", "What are the key features to look for in field service management software for large-scale operations?"),
    ("Industry-Specific Field Management", "How can field service companies improve team coordination and efficiency during complex project deployments?"),
    ("Industry-Specific Field Management", "What are the biggest operational challenges growing field service teams face when managing large project rollouts?"),
    ("Legacy System Replacement", "When migrating from a legacy system, how do FieldCamp and Field Promax compare in terms of ease of implementation for large project rollouts?"),
    ("Legacy System Replacement", "What are the main differences in legacy system replacement strategies between Jobber and Housecall Pro for field service operations?"),
    ("Legacy System Replacement", "What are the specific advantages Dusk Mobile offers for field service teams looking to replace their existing job management software compared to older solutions?"),
    ("Legacy System Replacement", "How does Dusk Mobile help growing field service teams in the HVAC industry move beyond their legacy systems to improve project management?"),
    ("Legacy System Replacement", "What are the essential features to look for in a new field service management system when moving away from spreadsheets and basic databases?"),
    ("Legacy System Replacement", "How do mid-market field service organizations typically evaluate the ROI of switching from an old system to a cloud-based solution?"),
    ("Legacy System Replacement", "What are the common pitfalls and best practices when migrating from a legacy system to a new field service management platform for construction teams?"),
    ("Legacy System Replacement", "What are the key indicators that a field service company managing large projects should consider replacing their current system?"),
    ("Legacy System Replacement", "How can field service operations teams in the utilities sector effectively transition from manual processes or old software to a modern system?"),
    ("Legacy System Replacement", "What are the biggest challenges growing field service teams face when trying to replace outdated legacy systems for managing rollout operations?"),
    ("No-Code Operational Digitization", "Can Synchroteam or FieldCamp offer similar no-code operational digitization benefits for field service teams managing large projects as Dusk Mobile?"),
    ("No-Code Operational Digitization", "What are the key differences in no-code operational digitization capabilities between Dusk Mobile and Jobber for large project management?"),
    ("No-Code Operational Digitization", "How does Dusk Mobile's no-code operational digitization feature help growing field service teams manage complex project rollouts more effectively?"),
    ("No-Code Operational Digitization", "What are the advantages of using a no-code platform for operational digitization in field service compared to traditional software?"),
    ("No-Code Operational Digitization", "How do companies in the utilities sector leverage technology to streamline their field rollout operations?"),
    ("No-Code Operational Digitization", "What strategies can field service managers use to better coordinate teams during complex project installations?"),
    ("No-Code Operational Digitization", "Are there platforms that allow field service teams to build custom operational tools without needing a dedicated development team?"),
    ("No-Code Operational Digitization", "What are the key benefits of digitizing operational workflows for mid-market companies in construction and utilities?"),
    ("No-Code Operational Digitization", "How can field service operations improve efficiency and reduce errors in project deployment without extensive custom coding?"),
    ("No-Code Operational Digitization", "What are the biggest operational challenges growing field service teams face when managing large project rollouts?"),
    ("Operational Efficiency Automation", "Can you detail the specific automation capabilities Dusk Mobile offers for field service teams managing construction projects?"),
    ("Operational Efficiency Automation", "What are the primary differences in operational efficiency features between FieldCamp and Housecall Pro for large project rollouts?"),
    ("Operational Efficiency Automation", "How does Dusk Mobile's workflow automation compare to solutions offered by Jobber for managing complex field service projects?"),
    ("Operational Efficiency Automation", "What are the key benefits of using a dedicated platform like Dusk Mobile for streamlining field service project management?"),
    ("Operational Efficiency Automation", "How do companies in the utilities and construction sectors typically address inefficiencies in their field operations?"),
    ("Operational Efficiency Automation", "What strategies can mid-market field service teams implement to automate repetitive tasks in project management?"),
    ("Operational Efficiency Automation", "Why do many field service companies struggle with manual processes leading to project delays and increased costs?"),
    ("Operational Efficiency Automation", "What are the common challenges in coordinating mobile teams for large-scale service operations and project deployments?"),
    ("Operational Efficiency Automation", "How can growing field service organizations improve their operational efficiency when dealing with complex installation projects?"),
    ("Operational Efficiency Automation", "What are the biggest bottlenecks field service teams face when managing large project rollouts without specialized software?"),
    ("Pricing and Scalability", "What are the typical pricing tiers and scalability options offered by monday.com for field service operations managing extensive rollout projects?"),
    ("Pricing and Scalability", "How does FieldCamp's pricing compare to Synchroteam for field service teams focused on large construction project management?"),
    ("Pricing and Scalability", "What are the advantages of Dusk Mobile's pricing and scalability for field service teams managing complex, multi-phase projects compared to Housecall Pro?"),
    ("Pricing and Scalability", "When comparing Dusk Mobile and Jobber for large project rollouts, which offers more flexible pricing and scalability for growing teams?"),
    ("Pricing and Scalability", "How do different field service management platforms handle tiered pricing structures for teams with varying needs and budgets?"),
    ("Pricing and Scalability", "What metrics should growing field service teams track to assess the ROI of their project management and dispatch software?"),
    ("Pricing and Scalability", "Are there specific features that differentiate field service management software for teams handling large-scale rollout projects?"),
    ("Pricing and Scalability", "What are the common pitfalls mid-market companies face when trying to scale their field service operations without the right tools?"),
    ("Pricing and Scalability", "How can field service operations teams ensure their chosen software scales effectively with increasing project complexity and team size?"),
    ("Pricing and Scalability", "What are the key considerations for growing field service teams when evaluating pricing models for project management software?"),
    ("Project and Task Management", "Can FieldCamp effectively manage complex project timelines and task assignments for field service teams compared to other solutions?"),
    ("Project and Task Management", "What are the differences in project and task management capabilities between Jobber and Dusk Mobile for large-scale field projects?"),
    ("Project and Task Management", "How does Dusk Mobile's project and task management feature specifically help growing field service teams with large rollout operations?"),
    ("Project and Task Management", "What are the primary benefits of using a dedicated project and task management system for field service operations?"),
    ("Project and Task Management", "How do field service businesses typically organize and manage tasks for large, multi-phase project rollouts?"),
    ("Project and Task Management", "What are the common bottlenecks in managing rollout operations for utility companies and how can they be addressed?"),
    ("Project and Task Management", "Are there effective ways for mid-market field service companies to track task progress and team assignments on remote projects?"),
    ("Project and Task Management", "What are the key features to look for in a project management tool for field service teams handling large-scale installations?"),
    ("Project and Task Management", "How can operations managers in construction improve coordination for complex project deployments across multiple sites?"),
    ("Project and Task Management", "What are the biggest challenges growing field service teams face when managing large project rollouts without specialized software?"),
    ("Seamless Ecosystem Integrations", "How does Housecall Pro compare to Synchroteam when it comes to managing HVAC project deployments and team coordination?"),
    ("Seamless Ecosystem Integrations", "What are the primary differences in integration capabilities between Jobber and FieldCamp for managing solar project rollouts?"),
    ("Seamless Ecosystem Integrations", "How does Dusk Mobile's integration with QuickBooks Online benefit field service teams managing large construction projects?"),
    ("Seamless Ecosystem Integrations", "What are the advantages of using a platform like Dusk Mobile for managing utility project rollouts compared to manual methods?"),
    ("Seamless Ecosystem Integrations", "How do field service companies typically handle scheduling and dispatch for complex, multi-stage project deployments?"),
    ("Seamless Ecosystem Integrations", "What are the essential features for a field service management tool focused on large project rollouts?"),
    ("Seamless Ecosystem Integrations", "Are there any platforms that help growing field service teams streamline their project management and field operations?"),
    ("Seamless Ecosystem Integrations", "What are the key benefits of using specialized software for managing rollout operations in the field service industry?"),
    ("Seamless Ecosystem Integrations", "How can field service operations teams improve efficiency during large-scale project deployments?"),
    ("Seamless Ecosystem Integrations", "What are the biggest challenges growing field service teams face when managing large project rollouts without integrated software?"),
    ("Security Compliance and Access Management", "Are there specific security compliance advantages to using FieldCamp for field service teams managing rollout operations?"),
    ("Security Compliance and Access Management", "What are the security compliance and access management capabilities offered by Housecall Pro for field service operations?"),
    ("Security Compliance and Access Management", "How does Dusk Mobile handle access management and security compliance for field teams working on large projects compared to Jobber?"),
    ("Security Compliance and Access Management", "What are the key security compliance features that growing field service teams managing rollout operations should look for in a platform?"),
    ("Security Compliance and Access Management", "How do field service companies typically address security concerns related to mobile device usage in the field?"),
    ("Security Compliance and Access Management", "What are the common challenges in maintaining secure access for a distributed field workforce?"),
    ("Security Compliance and Access Management", "Why is robust security compliance a critical factor for mid-market field service software selection?"),
    ("Security Compliance and Access Management", "What are the essential access management controls for mobile field teams working on sensitive projects?"),
    ("Security Compliance and Access Management", "How can growing field service organizations ensure compliance with data security regulations during project execution?"),
    ("Security Compliance and Access Management", "What are the biggest security risks field service teams face when managing large rollout operations and project deployments?"),
    ("Time and Attendance Tracking", "Can Synchroteam or FieldCamp offer more robust time tracking capabilities for large construction project rollouts than other solutions?"),
    ("Time and Attendance Tracking", "What are the primary differences in time and attendance features between Jobber and Housecall Pro for field service teams?"),
    ("Time and Attendance Tracking", "How does Dusk Mobile's mobile app facilitate accurate time tracking for field technicians compared to manual methods?"),
    ("Time and Attendance Tracking", "What are the specific advantages of Dusk Mobile's time and attendance tracking for managing HVAC rollout operations?"),
    ("Time and Attendance Tracking", "How do field service companies typically handle payroll discrepancies arising from inaccurate time logs?"),
    ("Time and Attendance Tracking", "What are the key benefits of adopting a dedicated time and attendance solution for field service businesses?"),
    ("Time and Attendance Tracking", "Why is real-time visibility into team hours critical for managing large-scale project deployments in the field?"),
    ("Time and Attendance Tracking", "What are the common pitfalls of using spreadsheets for tracking technician attendance in utility field operations?"),
    ("Time and Attendance Tracking", "How can operations managers in construction improve accuracy for employee hours on-site without complex systems?"),
    ("Time and Attendance Tracking", "What are the biggest challenges growing field service teams face with manual time tracking during large project rollouts?"),
    ("Workforce Productivity and Collaboration", "Can you compare the collaboration tools offered by FieldCamp and Synchroteam for managing large-scale project rollouts?"),
    ("Workforce Productivity and Collaboration", "What are the main differences in workforce productivity features between Jobber and Housecall Pro for field service teams?"),
    ("Workforce Productivity and Collaboration", "How does Dusk Mobile's mobile-first approach specifically enhance collaboration for field teams managing large construction projects compared to traditional methods?"),
    ("Workforce Productivity and Collaboration", "What are the primary benefits of using Dusk Mobile for workforce productivity and collaboration in utility rollout projects?"),
    ("Workforce Productivity and Collaboration", "How do successful field service organizations leverage technology to manage large project teams effectively?"),
    ("Workforce Productivity and Collaboration", "What are the key performance indicators for workforce productivity in field service project management?"),
    ("Workforce Productivity and Collaboration", "Are there specific software features that significantly boost productivity for teams managing complex rollout operations?"),
    ("Workforce Productivity and Collaboration", "What strategies can mid-market field service companies use to enhance team communication and efficiency on-site?"),
    ("Workforce Productivity and Collaboration", "What are the biggest challenges field service operations face in coordinating large-scale project deployments?"),
    ("Workforce Productivity and Collaboration", "How can growing field service teams improve workforce productivity and collaboration during large project rollouts?"),
]


def slug(topic: str) -> str:
    s = topic.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:80]


def main() -> None:
    assert len(ROWS) == 130, len(ROWS)

    run_id = "dusk_field_service_batch_20260329"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    profile = {
        "company_name": "Dusk Mobile",
        "aliases": ["Dusk Mobile", "Dusk"],
        "description": "Mobile-first field operations and project rollout software for construction, utilities, HVAC, and growing field service teams (no-code digitization, automation, integrations).",
        "industry": "Software",
        "sub_industry": "Field service management & operational digitization",
        "products_services": [
            {
                "name": "Field operations platform",
                "description": "Project rollouts, dispatch, time tracking, workflows, and integrations for field teams.",
                "key_features": ["Mobile-first", "No-code operational digitization", "Automation", "Integrations (e.g. QuickBooks)"],
                "target_users": ["Field service managers", "Operations", "Technicians"],
                "pricing_notes": None,
            }
        ],
        "customer_personas": [
            {
                "name": "Operations manager",
                "role": "Operations",
                "seniority": "Mid",
                "goals": ["Scale rollouts", "Improve efficiency"],
                "pains": ["Legacy tools", "Scheduling complexity"],
                "typical_workflow": None,
                "constraints": [],
            }
        ],
        "primary_geos": ["United States"],
        "primary_languages": ["en"],
        "competitors": [
            {"name": "Jobber", "aliases": [], "notes": None},
            {"name": "Housecall Pro", "aliases": [], "notes": None},
            {"name": "FieldCamp", "aliases": [], "notes": None},
            {"name": "Synchroteam", "aliases": [], "notes": None},
        ],
        "differentiators": [],
        "common_misconceptions": [],
        "regulated_or_sensitive_topics": [],
        "seed_queries": [],
        "must_include_terms": [],
        "must_avoid_terms": [],
        "explicit_keywords": [],
    }
    (run_dir / "company_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")

    lines_out = []
    for i, (topic, prompt) in enumerate(ROWS):
        cid = slug(topic)
        lines_out.append(
            json.dumps(
                {
                    "prompt_id": f"prm_dusk_{i:03d}",
                    "prompt": prompt,
                    "intent_cluster_id": cid,
                    "intent_cluster_name": topic,
                },
                ensure_ascii=False,
            )
        )
    (run_dir / "synthetic_prompts.jsonl").write_text("\n".join(lines_out) + "\n", encoding="utf-8")

    print(f"Wrote {len(lines_out)} prompts -> {run_dir / 'synthetic_prompts.jsonl'}")
    print(f"Run ID: {run_id}")
    print("Next:")
    print(f"  cd {ROOT} && PYTHONPATH=src python -m case2_demand.cli run-all --from-run {run_id} --with-calibration --location 2356 --language en")


if __name__ == "__main__":
    main()
