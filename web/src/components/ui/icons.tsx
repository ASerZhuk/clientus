import { Camera, Car, Clock, Drop, Shield, Sparkle, Star, User, Wrench, CheckCircle, ImagesSquare, Tag } from "@phosphor-icons/react";

const MAP = { shield: Shield, camera: Camera, clock: Clock, user: User, sparkle: Sparkle, star: Star, wrench: Wrench, car: Car, drop: Drop, check: CheckCircle, ImagesSquare, Tag } as const;

export function InfoIcon({ name, size = 22 }: { name: string; size?: number }) {
  const Icon = (MAP as Record<string, typeof Star>)[name] ?? Sparkle;
  return <Icon size={size} weight="duotone" aria-hidden />;
}
