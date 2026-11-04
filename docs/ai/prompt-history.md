# Prompt history

This is the record of every prompt I sent to the AI assistant (Claude Code) while building PAM, grouped by phase and in the order sent. It was compiled from the session transcript.

**How to read it**

- Wording is lightly edited for spelling and punctuation. Meaning is unchanged.
- Long pasted material (the written brief, cloud-console screenshots as text, security-rule listings) is summarised in italics rather than reproduced.
- Passwords and other credentials are omitted.
- Messages that only triggered a tool (interruptions, automatic task notifications, model switches) are not listed.
- Assistant replies and tool calls are not included. The commit history shows the work they produced.
- All prompts went to one tool, Claude Code. No other AI tool was used.

---

## 1. Scoping and planning

**P1. The brief.** *Pasted the written problem statement: categorise transactions, map recurring payments, compare household spending with budgets; four actor roles; nine entities with primary and foreign keys; deterministic IDs; step-by-step synthetic data instructions; labelled edge cases; required exports and evaluation outputs.*

**P2.** Wait, hold on.

**P3. (Brainstorming skill)** First brainstorm this end to end: Indian standards, UPI payments, server deployment on Linux. Make sure all edge cases are covered. Understand it fully and tell me before we decide what to do.

**P4.** Consumers don't put in that much effort. I need a simplified plan.

**P5.** It doesn't matter if we use the latest technologies; stick to FastAPI. I just want a normal, professional-grade piece of software. Everything runs on Linux, so we only have to run on it, and we can work out deployment steps later. Give me a proper walkthrough of the application's features, plus the plans.

**P6.** And the architecture as well.

**P7.** We will also build a small, efficient, smooth Android application, with Google sign-in through Firebase.

**P8.** It's not only the app. It also needs a FastAPI backend and a professional desktop web frontend.

**P9. (Writing-plans skill)** Write an end-to-end plan that doesn't miss a single edge case, and make sure the code architecture satisfies all of it.

**P10.** *(Interrupted the first attempt.)*

**P11. (Writing-plans skill)** Yes, please continue.

**P12.** Remember, I want the software as optimised as possible and production grade, without exaggerating the project. Use all the tricks that experienced software developers use for this kind of system.

**P13.** Remember that the frontend and UI play a key role.

**P14.** Change the name from "Kharcha" to PAM (it can stand for "Payment Account Manager"). Build inline here instead of using subagents. Always find all possible edge cases, document them and handle them as you build. Make everything interactive and not like AI-generated filler. Make sure everything is right.

**P15. (Executing-plans skill)** Execute the plan.

## 2. Infrastructure and database

**P16.** The server is reachable with `ssh vbs`. First check what is running on it and what links are connected.

**P17.** Use a local Postgres. *(Interrupted, then replaced by the next message.)*

**P18.** The database should live on the server as well. Please help me configure this domain. *(Pasted the domain registry dashboard to show the requested subdomain.)*

**P19.** Yes, continue. *(Approved the server and DNS steps.)*

**P20.** Yes, continue.

## 3. Product direction

**P21.** "Anyone with a Google account gets a household's data. A new Google user who isn't on your admin list becomes a customer and is linked to the first household nobody has claimed yet…" Why is it like that? A new login should get his own data. For the old data, give it an email and password login. We have a domain, so we can set up our own mail server too. And stop every service on the server that isn't part of this project, including the unrelated hosted sites.

**P22. (Answers to follow-up questions)** A new user's household should start empty. Users can also enter their own data, with optional fields. This is not just a display of synthetic data: it is a real application where users log in and use it. All sample households share one password: `password123`.

**P23.** I opened outbound and inbound port 25 in the cloud console, so please check. *(Pasted the network security-list rules twice.)*

**P24.** Yes, B19 and then deploy.

**P25.** Yes, web console.

## 4. Design direction

**P26. (Answers to design questions)** Primary user: household customer. Brand: no preference, you decide. Language and themes: English, light and dark. Chosen visual direction: "Hisaab Register" (a ledger-book look).

## 5. Completion

**P27.** Don't ask any questions. Proceed, implement everything, then build the APK as well. Deploy everything by tomorrow. You can also create a git repository, because this PC has git configured, and the key too.

## 6. Review and follow-up

**P28.** Why did it stop? And why is there no option to add records?

**P29.** *(Reply to the assistant's offer to make sample households writable.)* Also, how could that break the evaluation numbers?

**P30.** Have you put the Flutter code on git as well, and the APK on Releases? And can our website link be shown on the right side of the repository page?

**P31.** Does the brief say it is mandatory to mention a specific programme label everywhere?

**P32.** Remove that label from the README and the About box. Make it look like a professional application and its git repository, while keeping the current format. Also refine this prompt history so it looks professional.
