import type { Metadata } from "next";
import { MyBookings } from "@/components/client/MyBookings";

export const metadata: Metadata = { title: "Моя запись", robots: { index: false } };

export default function MyPage() {
  return <MyBookings />;
}
