import type { Metadata } from "next";
import { InstallGuide } from "@/components/client/InstallGuide";

export const metadata: Metadata = { title: "Добавить на экран" };

export default function InstallPage() {
  return <InstallGuide />;
}
