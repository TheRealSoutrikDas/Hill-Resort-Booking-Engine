import type { Metadata } from "next";
import styles from "../auth.module.css";

export const metadata: Metadata = { title: "How we use your details" };

// A short notice for the Digital Personal Data Protection Act, 2023 (A-161). The
// retention period and the grievance contact are CompanyA's to decide; they are listed
// as open items in the technical design document, not invented here.
export default function PrivacyPage() {
  return (
    <div className={`page ${styles.wrap}`}>
      <h1>How we use your details</h1>
      <h2>What we collect</h2>
      <p>
        When you create an account: your name, email address, a password (stored only as a secure
        hash) and, if you give it, your phone number. When you book: the name, email and phone
        number of the guest, your dates and rooms, and the payment status. When you send an
        enquiry: your message and contact details.
      </p>
      <h2>Why</h2>
      <p>
        To manage your account and bookings, to send you booking confirmations, and to reply to
        your enquiries. We do not use your details for marketing.
      </p>
      <h2>What we never collect online</h2>
      <p>No passport or ID details. Card details are handled by the payment provider, not by us.</p>
      <h2>Enquiries and our assistant</h2>
      <p>
        To route an enquiry to the right team, the text of your message may be sent to an AI
        service. Your name, email and phone number are never sent with it.
      </p>
      <h2>Your choices</h2>
      <p>
        To see, correct or delete your details, or to withdraw your consent, contact the resort.
      </p>
    </div>
  );
}
