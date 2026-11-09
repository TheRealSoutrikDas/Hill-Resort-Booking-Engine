import type { Metadata } from "next";
import { Suspense } from "react";
import styles from "../auth.module.css";
import { EnquiryForm } from "./EnquiryForm";

export const metadata: Metadata = { title: "Send an enquiry" };

export default function EnquirePage() {
  return (
    <div className={`page ${styles.wrap}`}>
      <h1>Send an enquiry</h1>
      <p className="muted">
        Weddings, company offsites, group stays, or anything else you would like to ask. Our team
        will reply.
      </p>
      <Suspense fallback={null}>
        <EnquiryForm />
      </Suspense>
    </div>
  );
}
