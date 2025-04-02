// filepath: /home/aryan/Downloads/Projects/crustdata-build-challenge/frontend/src/app/api/screenshots/[filename]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import axios from 'axios';

export async function GET(
    request: NextRequest,
    { params }: { params: { filename: string } }
) {
    const filename = params.filename;

    try {
        // Fetch the screenshot from the backend server
        const response = await axios({
            method: 'GET',
            url: `http://localhost:8000/screenshots/${filename}`,
            responseType: 'arraybuffer'
        });

        // Return the image with proper content type
        return new NextResponse(response.data, {
            headers: {
                'Content-Type': 'image/png',
                'Cache-Control': 'public, max-age=60'
            }
        });
    } catch (error) {
        console.error('Error fetching screenshot:', error);
        return new NextResponse('Failed to fetch screenshot', { status: 500 });
    }
}