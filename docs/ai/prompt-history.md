# Prompt history

This is the record of every prompt I sent to the AI assistant (Claude Code) while building PAM, grouped by phase and in the order sent. It was compiled from the session transcript.

**How to read it**

- Wording is lightly edited for spelling and punctuation. Meaning is unchanged.
- Long pasted material (the written brief, cloud-console screenshots as text, security-rule listings) is summarised in italics rather than reproduced.
- Passwords and other credentials are omitted.
- Messages that only triggered a tool (interruptions, automatic task notifications, model switches) are not listed.
- Assistant replies and tool calls are not included. The commit history shows the work they produced.
- Prompts to Claude Code are listed here. I also asked ChatGPT for advice on choosing an SMTP relay and pasted one of its replies into the session (P38). Those ChatGPT prompts were not exported, so they are not reproduced; the disclosure says so.

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

**P16.** The server is reachable over SSH for me. First let me check what is running on it and what links are connected.

**P17.** Use a local Postgres. *(Interrupted, then replaced by the next message.)*

**P18.** The database should live on the server as well. Please help me configure this domain. *(Pasted the domain registry dashboard to show the requested subdomain.)*

**P19.** Yes, continue. *(Approved the server and DNS steps.)*

**P20.** Yes, continue.

## 3. Product direction

**P21.** "Anyone with a Google account gets a household's data. A new Google user who isn't on your admin list becomes a customer and is linked to the first household nobody has claimed yet…" Why is it like that? A new login should get his own data. For the old data, give it an email and password login. We have a domain, so we can set up our own mail server too. And do let me stop every service on the server that isn't part of this project, including the unrelated hosted sites, ahh you can continue.

**P22. (Answers to follow-up questions)** A new user's household should start empty. Users can also enter their own data, with optional fields. This is not just a display of synthetic data: it is a real application where users log in and use it. All sample households share one password: `password123`.

**P23.** I opened outbound and inbound port 25 in the cloud console, so please use it to Setup SMTP. *(Pasted the network security-list rules twice.)*

**P24.** Yes, B19 and then deploy.

**P25.** Yes, web console.

## 4. Design direction

**P26. (Answers to design questions)** Primary user: household customer. Brand: no preference, you decide. Language and themes: English, light and dark. Chosen visual direction: "Hisaab Register" (a ledger-book look).

## 5. Completion

**P27.** Don't ask any questions. Proceed, implement everything, then lets build the APK as well. i'll Deploy everything by tomorrow. You can also create a git repository, because this PC has git configured, and the key too if u need any assistance let me know.

## 6. Review, naming and sign-off

**P28.** Why did it stop? And why is there no option to add records?

**P29.** *(Reply to the assistant's offer to make sample households writable.)* Also, how could that break the evaluation numbers?

**P30.** Have you pushed the Flutter code on git as well, and the APK on Releases? And can our website link be shown on the right side of the repository page?

**P31.** Does the brief say it is mandatory to mention a specific programme label everywhere? i don't think so.

**P32.** Remove that label from the README and the About box. Make it look like a professional application and its git repository, while keeping the current format. Also refine this architecture designs so it looks professional.

## 7. Mail and domain

**P33.** Why are you not relying on port 587? Do you want me to add its ingress and egress rules?

**P34.** All I have is that domain. We can't createSMTP and host on oracle; Coz i just realised oracle blocks port 25(SMTP) for free servers, I just got a domain.

**P35.** *(Screenshot of the DNS dashboard showing a second record I had created.)* I tried and got one.

**P36.** I think we can self-host Mailu on the Oracle server and control mailboxes, SMTP, IMAP and webmail maybe can use port 587 for it.

**P37.** *(Pasted a provider's question: complete email hosting, or SMTP only for notifications, OTPs and password resets.)*

**P38.** *(Pasted ChatGPT's recommendation of SMTP2GO with its free-plan limits and setup steps.)*

**P39.** Leave that. At least let me to set up Gmail SMTP.

**P40.** Done setting up. *(Pasted the connection check output.)* Also, here is the mail address to use. *(address redacted)*

**P41.** Have you added this SMTP setup and the server setup information to the documents on GitHub?

**P42.** Yes. Document it from server creation, then the security rules, getting the domain and where from, and the DNS setup too.

## 8. Remaining work and Google sign-in

**P43.** Not yet. First tell me what else is left on our code.

**P44.** *(Screenshot of the Firebase "lets Add Firebase to our Android app" step and the downloaded config file.)*

**P45.** I messed up. We need to change the Firebase config to a new one; that one belongs to another project.

**P46.** *(Screenshot and config from a new Firebase project.)* Use the same name and id as before. *(package id omitted)*

**P47.** *(Screenshots showing Google enabled and the release fingerprint added, plus the new config file.)*

**P48.** Make my own address the admin. *(address redacted)* Also install it on my phone using adb; the phone is connected to this PC.

**P49.** *(Screenshot of the web login saying Google sign-in is switched off.)* It's still off on the website.

**P50.** The Google sign-in redirects to Chrome instead of happening inside the app.

**P51.** Done working. Now what else is left to do?

**P52.** Proceed with the must-do list: test the README from a fresh clone, update the edge-case register, add CI, update the docs and prompt history. Also add welcome emails and so on, and tell me if anything else is left.

**P53.** Also add UPI accounts, with Paytm, PhonePe and so on and a custom option, alongside savings account and credit card.
