from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from services.file_upload_service import AttendanceFileUploadService
from models.attendance_models import UploadResponse
from config.auth import verify_api_key
import io
import pandas as pd

router = APIRouter(prefix="/upload", tags=["upload"])

@router.post("/attendance", dependencies=[Depends(verify_api_key)])
async def upload_attendance_file(file: UploadFile = File(...)):
    """
    Upload Excel/CSV file containing attendance data
    
    - **file**: Excel (.xlsx, .xls) or CSV file with attendance records
    
    Returns processed attendance records with validation results
    """
    if not file.filename:
        return {
            "success": False,
            "message": "No file selected",
            "error": "Please select a file to upload"
        }
    
    try:
        # Process the uploaded file
        result = await AttendanceFileUploadService.process_file(file)
        return {
            "success": True,
            "message": f"File '{file.filename}' uploaded and processed successfully!",
            "data": result,
            "records_processed": len(result.records) if hasattr(result, 'records') else 0
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to process file '{file.filename}'",
            "error": str(e)
        }

@router.get("/template")
async def download_template():
    """
    Download Excel template for attendance data upload
    
    Returns an Excel file with the correct column structure and sample data
    """
    try:
        # Generate template DataFrame
        template_df = AttendanceFileUploadService.generate_template()
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            template_df.to_excel(writer, sheet_name='Attendance Template', index=False)
        
        output.seek(0)
        
        # Return as downloadable file
        return StreamingResponse(
            io.BytesIO(output.read()),
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={"Content-Disposition": "attachment; filename=attendance_template.xlsx"}
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating template: {str(e)}"
        )

@router.get("/health")
async def health_check():
    """
    Health check endpoint for upload service
    """
    return {"status": "healthy", "service": "attendance_upload"}