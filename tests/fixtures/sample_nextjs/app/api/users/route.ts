import { NextRequest, NextResponse } from "next/server";

/**
 * List all users.
 */
export async function GET(req: NextRequest): Promise<NextResponse> {
    return NextResponse.json([]);
}

/**
 * Create a user.
 */
export async function POST(req: NextRequest): Promise<NextResponse> {
    const body = await req.json();
    return NextResponse.json({ id: 1, ...body }, { status: 201 });
}
