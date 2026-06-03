import { ProductionMeetingRoom } from "@/components/production/ProductionViews";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function MeetingPage({ params }: Props) {
  const { id } = await params;
  return <ProductionMeetingRoom roomId={id} />;
}
