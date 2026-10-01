import type { Metadata } from "next";
import { ServicesPanel } from "@/components/client/HomeSections";

export const metadata: Metadata = { title: "Услуги" };

export default function ServicesPage() {
  return (
    <>
      <h1 className="page title-xl" style={{ marginTop: 28 }}>Услуги и цены</h1>
      <p className="page lead" style={{ marginTop: 14 }}>Время включает работу с автомобилем. Стоимость уточняется после осмотра.</p>
      <ServicesPanel withHeading={false} />
    </>
  );
}
