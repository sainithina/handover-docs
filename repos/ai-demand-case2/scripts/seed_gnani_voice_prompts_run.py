#!/usr/bin/env python3
"""Seed run dir: Gnani / enterprise voice AI prompt batch → synthetic_prompts.jsonl + company_profile."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROWS: list[tuple[str, str]] = [
    ("Advanced AI Agent Capabilities", "What are the integration capabilities of Uniphore's AI agents with existing contact center infrastructure?"),
    ("Advanced AI Agent Capabilities", "How does Yellow.ai's AI agent technology compare to Kore.ai for enterprise customer experience automation?"),
    ("Advanced AI Agent Capabilities", "What are the specific benefits of Gnani.ai's AI agents for improving customer satisfaction in telecom call centers?"),
    ("Advanced AI Agent Capabilities", "How does Gnani.ai's advanced AI agent technology handle complex customer service scenarios in banking?"),
    ("Advanced AI Agent Capabilities", "What are the primary challenges companies face when implementing voice AI for customer experience?"),
    ("Advanced AI Agent Capabilities", "How do advanced AI agents differ from traditional chatbots in enterprise settings?"),
    ("Advanced AI Agent Capabilities", "What are the latest advancements in AI agent technology for handling complex customer queries?"),
    ("Advanced AI Agent Capabilities", "What are the benefits of using voice AI for customer service in financial institutions?"),
    ("Advanced AI Agent Capabilities", "How can enterprise customer experience automation improve efficiency in telecom contact centers?"),
    ("Advanced AI Agent Capabilities", "What are the key capabilities of advanced AI agents for automating customer interactions in the BFSI sector?"),
    ("Agentic AI for Enterprise Automation", "What are the latest advancements in voice AI for contact centers, and how do platforms like Uniphore and PolyAI address them?"),
    ("Agentic AI for Enterprise Automation", "How does Yellow.ai's approach to enterprise voice AI compare with Kore.ai's capabilities for customer experience automation?"),
    ("Agentic AI for Enterprise Automation", "What are the specific advantages of using Gnani.ai for voice AI automation in BFSI compliance and customer service?"),
    ("Agentic AI for Enterprise Automation", "How does Gnani.ai's agentic AI approach differ from traditional voice AI solutions for enterprise automation?"),
    ("Agentic AI for Enterprise Automation", "What are the essential features to look for in an enterprise customer experience automation platform for voice interactions?"),
    ("Agentic AI for Enterprise Automation", "How do advanced voice AI platforms contribute to reducing operational costs in telecommunications customer support?"),
    ("Agentic AI for Enterprise Automation", "What are the benefits of using AI-powered voice bots for handling complex customer queries in financial services?"),
    ("Agentic AI for Enterprise Automation", "What are the key considerations for implementing enterprise-grade voice AI for customer interaction automation?"),
    ("Agentic AI for Enterprise Automation", "How can agentic AI solutions improve efficiency and customer satisfaction in large contact center operations?"),
    ("Agentic AI for Enterprise Automation", "What are the primary challenges enterprises face in automating customer experience through voice AI in the BFSI and telecom sectors?"),
    ("AI Strategy and Best Practices", "How can businesses ensure robust compliance and security when implementing voice AI solutions for sensitive customer data in BFSI?"),
    ("AI Strategy and Best Practices", "What are the primary advantages of Yellow.ai's AI strategy for customer experience automation compared to other market players?"),
    ("AI Strategy and Best Practices", "How does Gnani.ai's approach to AI strategy differ from competitors like Kore.ai or Uniphore in terms of enterprise deployment?"),
    ("AI Strategy and Best Practices", "What are the specific benefits and potential drawbacks of using enterprise-grade voice AI for customer onboarding in the BFSI sector?"),
    ("AI Strategy and Best Practices", "How do different AI strategies impact the ROI for customer service automation in highly regulated industries like finance?"),
    ("AI Strategy and Best Practices", "What are the common challenges faced by large organizations when adopting advanced AI for customer experience and how can they be overcome?"),
    ("AI Strategy and Best Practices", "When evaluating voice AI platforms, what are the critical factors for ensuring successful integration into existing enterprise workflows?"),
    ("AI Strategy and Best Practices", "What are the leading best practices for implementing voice AI solutions in contact centers to reduce agent workload and boost customer satisfaction?"),
    ("AI Strategy and Best Practices", "How can enterprises in the telecom industry best leverage voice AI for automating customer interactions and improving operational efficiency?"),
    ("AI Strategy and Best Practices", "What are the key considerations for developing an effective AI strategy in the BFSI sector to enhance customer experience automation?"),
    ("AI-Driven Collections and Revenue Recovery", "Can PolyAI's voice AI effectively automate collections for mid-market financial institutions, and what are the typical implementation timelines?"),
    ("AI-Driven Collections and Revenue Recovery", "What are the primary advantages of using Uniphore's AI for revenue recovery compared to Skit.ai in telecom?"),
    ("AI-Driven Collections and Revenue Recovery", "How does Gnani.ai's voice AI compare to solutions from Yellow.ai or Kore.ai for automating collections in BFSI?"),
    ("AI-Driven Collections and Revenue Recovery", "What are the specific benefits of using Gnani.ai for AI-driven collections and revenue recovery in enterprise contact centers?"),
    ("AI-Driven Collections and Revenue Recovery", "How does voice AI technology assist in identifying and mitigating revenue leakage in financial services?"),
    ("AI-Driven Collections and Revenue Recovery", "What strategies can be employed to enhance customer engagement during debt collection calls using AI?"),
    ("AI-Driven Collections and Revenue Recovery", "Are there AI tools that can help telecom companies reduce call handling time for overdue payments?"),
    ("AI-Driven Collections and Revenue Recovery", "What are the key performance indicators for successful revenue recovery automation in contact centers?"),
    ("AI-Driven Collections and Revenue Recovery", "How can AI-powered voice solutions improve the efficiency of debt collection processes in the BFSI sector?"),
    ("AI-Driven Collections and Revenue Recovery", "What are the biggest challenges enterprises face in automating collections and recovering revenue through voice channels?"),
    ("Conversation Analytics and QA", "What are the latest advancements in voice AI for contact centers, and how do Uniphore and PolyAI compare?"),
    ("Conversation Analytics and QA", "How does Yellow.ai's approach to conversation analytics differ from Kore.ai in terms of enterprise QA?"),
    ("Conversation Analytics and QA", "What are the advantages of using Gnani.ai's voice AI for automating customer service compared to manual processes?"),
    ("Conversation Analytics and QA", "How does Gnani.ai's conversation analytics specifically help BFSI companies with compliance monitoring and agent QA?"),
    ("Conversation Analytics and QA", "What are the essential features to look for in a conversation analytics tool for enterprise customer experience automation?"),
    ("Conversation Analytics and QA", "What are the primary challenges faced by contact centers when trying to analyze customer conversations at scale?"),
    ("Conversation Analytics and QA", "How do enterprise-grade voice AI platforms typically handle quality assurance for agent performance?"),
    ("Conversation Analytics and QA", "What are the most effective strategies for automating customer experience in telecommunications using AI?"),
    ("Conversation Analytics and QA", "How can businesses in the BFSI sector leverage voice AI to improve customer interactions and compliance?"),
    ("Conversation Analytics and QA", "What are the key benefits of using conversation analytics for quality assurance in large contact centers?"),
    ("Enterprise Deployment and Integration", "What are the primary differences in managed services and implementation support between Uniphore and Skit.ai for enterprise voice AI adoption?"),
    ("Enterprise Deployment and Integration", "How does Yellow.ai compare to Kore.ai in terms of enterprise deployment flexibility and integration capabilities for voice AI solutions?"),
    ("Enterprise Deployment and Integration", "What specific features does Gnani.ai offer to ensure seamless omnichannel integration for large-scale contact center operations?"),
    ("Enterprise Deployment and Integration", "How does Gnani.ai's enterprise deployment strategy address the complexities of integrating with legacy systems in the BFSI sector?"),
    ("Enterprise Deployment and Integration", "What are the most effective strategies for leveraging voice AI to enhance customer satisfaction in regulated industries like banking and insurance?"),
    ("Enterprise Deployment and Integration", "How do leading voice AI platforms ensure data security and compliance with regulations like GDPR and PCI DSS in contact center environments?"),
    ("Enterprise Deployment and Integration", "What are the typical implementation timelines and challenges when adopting enterprise-grade voice AI for customer support operations?"),
    ("Enterprise Deployment and Integration", "What are the benefits of deploying omnichannel customer experience automation for BFSI companies looking to improve customer engagement?"),
    ("Enterprise Deployment and Integration", "How can businesses in the telecom sector automate customer service workflows using advanced voice AI platforms to reduce operational costs?"),
    ("Enterprise Deployment and Integration", "What are the key considerations for integrating enterprise voice AI solutions into existing contact center infrastructure for large financial institutions?"),
    ("Industry-Specific AI Solutions", "How does Uniphore's platform for conversational automation stack up against Skit.ai for contact center efficiency?"),
    ("Industry-Specific AI Solutions", "What are the pros and cons of using Yellow.ai versus Kore.ai for enterprise-level customer experience automation in telecom?"),
    ("Industry-Specific AI Solutions", "How does Gnani.ai's approach to voice biometrics for authentication compare to other solutions in the market for fraud detection?"),
    ("Industry-Specific AI Solutions", "What are the main differences between enterprise voice AI solutions like Gnani.ai and more basic chatbot platforms for customer service?"),
    ("Industry-Specific AI Solutions", "How do businesses typically measure the ROI of customer experience automation platforms in the BFSI sector?"),
    ("Industry-Specific AI Solutions", "What are the most effective strategies for integrating AI voice solutions into existing CRM and telephony systems?"),
    ("Industry-Specific AI Solutions", "Explain the role of conversational AI in reducing operational costs for enterprise customer support departments."),
    ("Industry-Specific AI Solutions", "What are the key benefits of implementing omnichannel customer experience automation for large contact centers?"),
    ("Industry-Specific AI Solutions", "How can BFSI and telecom companies improve customer satisfaction scores using AI-powered voice interactions?"),
    ("Industry-Specific AI Solutions", "What are the primary challenges enterprises face in automating customer experience across voice, chat, and SMS channels today?"),
    ("Linguistic and Domain Accuracy", "How can PolyAI or SoundHound AI improve their domain-specific accuracy for handling complex financial transactions in voice-based customer interactions?"),
    ("Linguistic and Domain Accuracy", "What are the primary reasons why companies like Yellow.ai or Skit.ai struggle with maintaining consistent linguistic accuracy across different customer service channels?"),
    ("Linguistic and Domain Accuracy", "How does Gnani.ai's approach to voice AI accuracy compare to solutions offered by competitors like Kore.ai or Uniphore for telecom use cases?"),
    ("Linguistic and Domain Accuracy", "What specific advancements in Natural Language Understanding does Gnani.ai offer to ensure superior linguistic and domain accuracy for BFSI clients?"),
    ("Linguistic and Domain Accuracy", "How do enterprise customer experience automation platforms address the need for precise language understanding in high-volume contact center environments?"),
    ("Linguistic and Domain Accuracy", "What are the common pitfalls in training voice AI models to understand and respond appropriately to customer queries in the insurance domain?"),
    ("Linguistic and Domain Accuracy", "Why is it difficult for current voice AI platforms to maintain high accuracy when handling sensitive customer data in regulated industries like banking?"),
    ("Linguistic and Domain Accuracy", "What are the key considerations for ensuring domain-specific accuracy in voice AI solutions for telecommunications customer support?"),
    ("Linguistic and Domain Accuracy", "How can contact centers improve the linguistic accuracy of AI agents when dealing with diverse accents and regional dialects in the BFSI sector?"),
    ("Linguistic and Domain Accuracy", "What are the biggest challenges companies face in achieving accurate voice recognition for complex financial jargon in customer service interactions?"),
    ("Multilingual and Omnichannel Support", "Compare the effectiveness of PolyAI's and SoundHound AI's solutions for providing omnichannel customer service in diverse linguistic markets."),
    ("Multilingual and Omnichannel Support", "What are the main differences in multilingual support capabilities between Uniphore and Skit.ai for enterprise contact centers?"),
    ("Multilingual and Omnichannel Support", "How does Gnani.ai's approach to omnichannel support differ from competitors like Yellow.ai or Kore.ai in terms of language flexibility and integration capabilities?"),
    ("Multilingual and Omnichannel Support", "What specific advantages does Gnani.ai offer for enterprises needing to manage customer interactions in over 20 languages simultaneously across voice and digital channels?"),
    ("Multilingual and Omnichannel Support", "How do businesses typically measure the success of their multilingual and omnichannel customer support initiatives?"),
    ("Multilingual and Omnichannel Support", "What are the best practices for ensuring seamless customer journeys when interacting through various digital and voice channels?"),
    ("Multilingual and Omnichannel Support", "Explore the impact of multilingual voice AI on customer satisfaction and operational efficiency in global telecommunications companies."),
    ("Multilingual and Omnichannel Support", "What are the key benefits of implementing an omnichannel customer engagement strategy for large enterprises in the financial sector?"),
    ("Multilingual and Omnichannel Support", "How can contact centers improve customer experience by integrating voice AI solutions that support a wide range of languages and communication methods?"),
    ("Multilingual and Omnichannel Support", "What are the primary challenges businesses face when trying to offer consistent customer support across multiple languages and channels like voice, chat, and SMS?"),
    ("Operational Cost and Efficiency Gains", "What are the typical implementation costs and potential ROI for voice AI solutions like Uniphore in the telecom industry?"),
    ("Operational Cost and Efficiency Gains", "How do Yellow.ai and Kore.ai compare in terms of their ability to deliver operational cost efficiencies for enterprise clients?"),
    ("Operational Cost and Efficiency Gains", "What are the real-world examples of operational cost savings achieved by using Gnani.ai in a large contact center environment?"),
    ("Operational Cost and Efficiency Gains", "How does Gnani.ai's voice AI platform specifically help BFSI companies reduce operational costs and improve efficiency?"),
    ("Operational Cost and Efficiency Gains", "What are the common challenges faced by enterprises when trying to achieve operational efficiency through voice automation?"),
    ("Operational Cost and Efficiency Gains", "How does implementing voice AI impact the overall operational budget of a mid-market enterprise?"),
    ("Operational Cost and Efficiency Gains", "Are there specific voice AI technologies that offer significant operational cost reductions for large contact centers?"),
    ("Operational Cost and Efficiency Gains", "What are the key metrics for measuring efficiency gains in telecom customer service operations using AI?"),
    ("Operational Cost and Efficiency Gains", "How can businesses in the BFSI sector reduce expenses through voice AI solutions for customer interactions?"),
    ("Operational Cost and Efficiency Gains", "What are the primary drivers of operational cost in enterprise contact centers, and how can automation address them?"),
    ("Platform Evaluation and Demo", "Can Yellow.ai handle complex voice-based customer service workflows for large insurance providers as effectively as other leading solutions?"),
    ("Platform Evaluation and Demo", "What are the primary differences in platform capabilities between Uniphore and Skit.ai for contact center automation?"),
    ("Platform Evaluation and Demo", "What are the specific advantages of using Gnani.ai's voice AI for fraud detection in BFSI compared to manual processes?"),
    ("Platform Evaluation and Demo", "How does Gnani.ai's platform compare to Kore.ai for enterprise-level voice AI deployments in banking?"),
    ("Platform Evaluation and Demo", "What are the essential components of a robust voice AI platform for financial services?"),
    ("Platform Evaluation and Demo", "How do different enterprise voice AI platforms compare in terms of scalability and features for customer experience?"),
    ("Platform Evaluation and Demo", "What are the main challenges companies face when implementing voice AI for customer support?"),
    ("Platform Evaluation and Demo", "What are the benefits of using AI for automating customer interactions in contact centers?"),
    ("Platform Evaluation and Demo", "How can voice AI solutions improve customer service efficiency in large telecom companies?"),
    ("Platform Evaluation and Demo", "What are the key considerations for enterprise customer experience automation platforms in the BFSI sector?"),
    ("Real-Time Agent Assistance", "What are the main differences between Yellow.ai and Kore.ai when it comes to real-time agent assistance for enterprise customer experience?"),
    ("Real-Time Agent Assistance", "How does Uniphore's real-time agent assistance compare to other solutions in terms of agent coaching and performance improvement?"),
    ("Real-Time Agent Assistance", "What are the integration capabilities of Gnani.ai for real-time agent assistance within existing contact center infrastructure?"),
    ("Real-Time Agent Assistance", "How does Gnani.ai's Real-Time Agent Assistance feature help agents provide more accurate and faster responses during customer calls?"),
    ("Real-Time Agent Assistance", "What are the typical challenges faced by enterprise customer experience automation platforms in the BFSI sector?"),
    ("Real-Time Agent Assistance", "How do real-time agent assistance systems contribute to better compliance and reduced errors in customer service calls?"),
    ("Real-Time Agent Assistance", "Looking for best practices in voice AI for contact centers to provide agents with immediate support during customer interactions."),
    ("Real-Time Agent Assistance", "What are the key benefits of implementing real-time agent assistance in telecom customer support operations?"),
    ("Real-Time Agent Assistance", "How can enterprise customer experience automation tools help BFSI companies reduce call handling times and improve agent efficiency?"),
    ("Real-Time Agent Assistance", "What are the most effective real-time agent assistance strategies for improving customer satisfaction in high-volume contact centers?"),
    ("Security and Compliance Standards", "How does Kore.ai ensure compliance with data residency and privacy laws for its voice AI solutions in the telecom sector?"),
    ("Security and Compliance Standards", "What security certifications does Uniphore offer to assure enterprise clients in regulated industries like banking and insurance?"),
    ("Security and Compliance Standards", "How does Gnani.ai address the security and compliance requirements for BFSI clients, particularly regarding sensitive financial data?"),
    ("Security and Compliance Standards", "What are the implications of SOC2 and ISO 27001 compliance for enterprise customer experience automation in voice AI?"),
    ("Security and Compliance Standards", "How do different voice AI solutions approach compliance with industry-specific regulations for customer interactions?"),
    ("Security and Compliance Standards", "What are the best practices for securing sensitive customer data within an enterprise voice AI platform?"),
    ("Security and Compliance Standards", "Are there specific compliance certifications that are critical for voice AI providers serving financial institutions?"),
    ("Security and Compliance Standards", "What are the common security vulnerabilities found in contact center automation software and how can they be mitigated?"),
    ("Security and Compliance Standards", "How can businesses in the telecom industry ensure their voice AI solutions meet stringent data privacy regulations like GDPR?"),
    ("Security and Compliance Standards", "What are the key security and compliance standards that enterprise customer experience automation platforms must adhere to in the BFSI sector?"),
    ("Voice AI Vendor Comparisons", "Are there any known issues or limitations with Uniphore's voice AI platform when used for complex BFSI compliance tasks?"),
    ("Voice AI Vendor Comparisons", "What are the advantages of using Yellow.ai's voice AI for customer service automation compared to other platforms in the market?"),
    ("Voice AI Vendor Comparisons", "How does Gnani.ai's approach to omnichannel integration compare to solutions offered by Kore.ai for enterprise contact centers?"),
    ("Voice AI Vendor Comparisons", "What specific voice AI features does Gnani.ai offer for fraud detection and customer authentication in banking applications?"),
    ("Voice AI Vendor Comparisons", "How can businesses leverage voice AI to improve agent efficiency and reduce operational costs in large-scale contact centers?"),
    ("Voice AI Vendor Comparisons", "What are the essential features to look for in a voice AI platform for enhancing customer engagement in financial services?"),
    ("Voice AI Vendor Comparisons", "Can you explain the typical ROI and implementation timelines for enterprise-grade voice AI solutions in the telecom sector?"),
    ("Voice AI Vendor Comparisons", "What are the primary challenges businesses face when implementing voice AI for customer experience automation in regulated industries?"),
    ("Voice AI Vendor Comparisons", "How do mid-market contact centers typically evaluate voice AI platforms for automating customer interactions across multiple channels?"),
    ("Voice AI Vendor Comparisons", "What are the key differences in voice AI capabilities between enterprise solutions like Gnani.ai and other leading providers for BFSI customer service?"),
    ("Voice Biometrics and Fraud Prevention", "How does Kore.ai's approach to voice biometrics address the challenges of fraud prevention in enterprise customer experience?"),
    ("Voice Biometrics and Fraud Prevention", "What are the advantages of using Yellow.ai's voice AI for fraud prevention compared to traditional security measures?"),
    ("Voice Biometrics and Fraud Prevention", "How does Gnani.ai's voice biometrics solution compare to Uniphore's offerings for fraud detection in contact centers?"),
    ("Voice Biometrics and Fraud Prevention", "What are the specific voice biometric capabilities offered by Gnani.ai for enterprise fraud prevention in the BFSI sector?"),
    ("Voice Biometrics and Fraud Prevention", "How do voice AI platforms help contact centers meet compliance requirements related to fraud prevention and data security?"),
    ("Voice Biometrics and Fraud Prevention", "What are the benefits of using voice biometrics for customer authentication in the BFSI sector to improve security?"),
    ("Voice Biometrics and Fraud Prevention", "Can voice AI solutions accurately identify and flag suspicious caller behavior in real-time for telecom companies?"),
    ("Voice Biometrics and Fraud Prevention", "What are the key considerations for implementing voice biometrics in a large-scale enterprise environment for fraud detection?"),
    ("Voice Biometrics and Fraud Prevention", "How can contact centers leverage voice AI to enhance security and reduce fraudulent activities during customer interactions?"),
    ("Voice Biometrics and Fraud Prevention", "What are the most effective methods for preventing account takeovers in financial services using voice biometrics technology?"),
    ("Voice-to-Voice AI Technology", "Compare the voice-to-voice AI solutions offered by Uniphore and PolyAI for customer experience automation in the telecom industry."),
    ("Voice-to-Voice AI Technology", "What are the main differences in voice AI capabilities between Yellow.ai and Kore.ai for enterprise contact centers?"),
    ("Voice-to-Voice AI Technology", "How does Gnani.ai's platform address the challenges of implementing voice AI in BFSI customer interactions compared to competitors?"),
    ("Voice-to-Voice AI Technology", "What are the specific advantages of Gnani.ai's voice-to-voice AI technology for enterprise customer experience automation?"),
    ("Voice-to-Voice AI Technology", "How does voice AI technology contribute to enhancing customer satisfaction in regulated industries like banking?"),
    ("Voice-to-Voice AI Technology", "What are the typical use cases for voice AI in contact centers aiming to reduce operational costs?"),
    ("Voice-to-Voice AI Technology", "Explain the benefits of using voice-to-voice AI for automating customer service interactions across different channels."),
    ("Voice-to-Voice AI Technology", "What are the key considerations for implementing voice AI technology in financial services for customer support?"),
    ("Voice-to-Voice AI Technology", "How can enterprise customer experience automation platforms improve efficiency in telecom contact centers?"),
    ("Voice-to-Voice AI Technology", "What are the primary challenges businesses face when trying to automate customer interactions using voice AI in the BFSI sector?"),
]


def slug(topic: str) -> str:
    s = topic.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:80]


def main() -> None:
    assert len(ROWS) == 160, len(ROWS)

    run_id = "gnani_voice_cx_batch_20260329"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    profile = {
        "company_name": "Gnani.ai",
        "aliases": ["Gnani", "Gnani.ai"],
        "description": "Enterprise voice AI and conversational automation for BFSI, telecom, and contact centers—agent assistance, collections, voice biometrics, omnichannel CX, and compliance-focused deployments.",
        "industry": "Software",
        "sub_industry": "Enterprise voice AI & customer experience automation",
        "products_services": [
            {
                "name": "Voice AI platform",
                "description": "Voice bots, real-time agent assist, analytics, and integrations for regulated contact centers.",
                "key_features": ["Voice AI", "Agent assistance", "Collections", "Voice biometrics", "Omnichannel"],
                "target_users": ["CX leaders", "Contact center ops", "BFSI IT"],
                "pricing_notes": None,
            }
        ],
        "customer_personas": [
            {
                "name": "VP Customer Experience",
                "role": "CX",
                "seniority": "Executive",
                "goals": ["Automate voice CX", "Reduce cost", "Stay compliant"],
                "pains": ["Legacy IVR", "Vendor evaluation"],
                "typical_workflow": None,
                "constraints": [],
            }
        ],
        "primary_geos": ["India", "United States"],
        "primary_languages": ["en"],
        "competitors": [
            {"name": "Uniphore", "aliases": [], "notes": None},
            {"name": "Yellow.ai", "aliases": [], "notes": None},
            {"name": "Kore.ai", "aliases": [], "notes": None},
            {"name": "PolyAI", "aliases": [], "notes": None},
            {"name": "Skit.ai", "aliases": [], "notes": None},
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
        lines_out.append(
            json.dumps(
                {
                    "prompt_id": f"prm_gnani_{i:03d}",
                    "prompt": prompt,
                    "intent_cluster_id": slug(topic),
                    "intent_cluster_name": topic,
                },
                ensure_ascii=False,
            )
        )
    (run_dir / "synthetic_prompts.jsonl").write_text("\n".join(lines_out) + "\n", encoding="utf-8")

    print(f"Wrote {len(lines_out)} prompts -> {run_dir / 'synthetic_prompts.jsonl'}")
    print(f"Run ID: {run_id}")


if __name__ == "__main__":
    main()
