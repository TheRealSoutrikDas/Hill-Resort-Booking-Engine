import type { Metadata } from "next";
import { EnquiryView } from "./EnquiryView";

export const metadata: Metadata = { title: "Enquiry" };

export default function EnquiryPage() {
  return <EnquiryView />;
}
