import type { Metadata } from "next";
import { Suspense } from "react";
import { PhotoPanel } from "@/components/PhotoPanel";
import { PANEL_ENQUIRE } from "@/lib/photos";
import { EnquiryForm } from "./EnquiryForm";

export const metadata: Metadata = { title: "Send an enquiry" };

export default function EnquirePage() {
  return (
    <PhotoPanel photo={PANEL_ENQUIRE}>
      <h1>Send an enquiry</h1>
      <p className="muted">
        Weddings, company offsites, group stays, or anything else you would like to ask. Our team
        will reply.
      </p>
      <Suspense fallback={null}>
        <EnquiryForm />
      </Suspense>
    </PhotoPanel>
  );
}
