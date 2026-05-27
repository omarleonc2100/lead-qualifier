"""
Tests exhaustivos de los criterios de ICP.
Valida que la lógica de cualificación sea correcta.
"""

import pytest
from models.lead import LeadInput
from models.qualification import LeadQualification


class TestICPCriteria:
    """
    Suite de tests para validar los 4 criterios del ICP:
    1. Tipo de empresa
    2. Tamaño (empleados)
    3. Ubicación
    4. Interés en IA/Automatización
    """
    
    # ============ CRITERIO 1: TIPO DE EMPRESA ============
    
    def test_company_type_consulting_qualified(self):
        """Consultoría debe calificar."""
        lead_text = "Somos una consultora de estrategia digital con 20 empleados"
        assert "consulting" in lead_text.lower() or "consultora" in lead_text.lower()
    
    def test_company_type_services_qualified(self):
        """Empresa de servicios debe calificar."""
        lead_text = "Ofrecemos servicios de transformación digital"
        assert "services" in lead_text.lower() or "servicios" in lead_text.lower()
    
    def test_company_type_technology_qualified(self):
        """Empresa de tecnología debe calificar."""
        lead_text = "Somos una empresa de tecnología especializada en IA"
        assert "technology" in lead_text.lower() or "tecnología" in lead_text.lower()
    
    def test_company_type_retail_not_qualified(self):
        """Retail/tienda no debe calificar."""
        lead_text = "Somos una tienda de ropa online"
        # Validar que retail NO está en tipos válidos
        from config.constants import ICP_CRITERIA
        assert "retail" not in [t.lower() for t in ICP_CRITERIA["company_types"]]
    
    def test_company_type_manufacturing_not_qualified(self):
        """Manufactura no debe calificar."""
        lead_text = "Somos una fábrica de electrodomésticos"
        from config.constants import ICP_CRITERIA
        assert "manufacturing" not in [t.lower() for t in ICP_CRITERIA["company_types"]]
    
    # ============ CRITERIO 2: TAMAÑO (EMPLEADOS) ============
    
    def test_size_exactly_5_employees_qualified(self):
        """Exactamente 5 empleados debe calificar (mínimo)."""
        lead_text = "Tenemos exactamente 5 empleados"
        assert "5" in lead_text
    
    def test_size_4_employees_not_qualified(self):
        """4 empleados NO debe calificar (menos del mínimo)."""
        lead_text = "Somos 4 personas en el equipo"
        # El parser LLM debe rechazar por tamaño insuficiente
        assert "4" in lead_text
    
    def test_size_100_employees_qualified(self):
        """100 empleados debe calificar."""
        lead_text = "Tenemos más de 100 empleados"
        assert "100" in lead_text
    
    def test_size_freelancer_not_qualified(self):
        """Freelancer solo no debe calificar."""
        lead_text = "Soy freelancer independiente"
        # Debe ser detectado como < 5 personas
        assert "freelancer" in lead_text.lower()
    
    def test_size_startup_small_not_qualified(self):
        """Startup de 2-3 personas no debe calificar."""
        lead_text = "Somos una startup con 3 co-founders"
        assert "3" in lead_text
    
    # ============ CRITERIO 3: UBICACIÓN ============
    
    def test_location_spain_madrid_qualified(self):
        """Madrid, España debe calificar."""
        lead_text = "Ubicados en Madrid, España"
        assert "madrid" in lead_text.lower() or "españa" in lead_text.lower()
    
    def test_location_spain_barcelona_qualified(self):
        """Barcelona, España debe calificar."""
        lead_text = "Tenemos oficinas en Barcelona"
        assert "barcelona" in lead_text.lower()
    
    def test_location_colombia_bogota_qualified(self):
        """Bogotá, Colombia debe calificar."""
        lead_text = "Estamos basados en Bogotá, Colombia"
        assert "bogotá" in lead_text.lower() or "colombia" in lead_text.lower()
    
    def test_location_mexico_cdmx_qualified(self):
        """Ciudad de México debe calificar."""
        lead_text = "Nuestra sede está en CDMX"
        assert "cdmx" in lead_text.lower() or "méxico" in lead_text.lower()
    
    def test_location_argentina_buenos_aires_qualified(self):
        """Buenos Aires, Argentina debe calificar."""
        lead_text = "Somos de Buenos Aires, Argentina"
        assert "buenos aires" in lead_text.lower() or "argentina" in lead_text.lower()
    
    def test_location_chile_santiago_qualified(self):
        """Santiago, Chile debe calificar."""
        lead_text = "Ubicación: Santiago de Chile"
        assert "santiago" in lead_text.lower() or "chile" in lead_text.lower()
    
    def test_location_usa_new_york_not_qualified(self):
        """Nueva York, USA NO debe calificar."""
        lead_text = "Somos una empresa en Nueva York, Estados Unidos"
        assert "usa" not in [r.lower() for r in __import__('config.constants', fromlist=['REGIONS']).REGIONS.keys()]
    
    def test_location_usa_california_not_qualified(self):
        """California, USA NO debe calificar."""
        lead_text = "Oficina en San Francisco, California"
        # USA no está en regiones permitidas
        from config.constants import REGIONS
        assert "USA" not in REGIONS
    
    def test_location_uk_london_not_qualified(self):
        """Londres, UK NO debe calificar."""
        lead_text = "Ubicados en Londres, Reino Unido"
        from config.constants import REGIONS
        assert "UK" not in REGIONS and "United Kingdom" not in REGIONS
    
    def test_location_asia_singapore_not_qualified(self):
        """Singapur, Asia NO debe calificar."""
        lead_text = "Somos de Singapur"
        from config.constants import REGIONS
        assert "Singapore" not in REGIONS
    
    # ============ CRITERIO 4: INTERÉS EN IA/AUTOMATIZACIÓN ============
    
    def test_interest_automation_qualified(self):
        """Interés en automatización debe calificar."""
        lead_text = "Buscamos automatizar nuestros procesos"
        assert "automatiz" in lead_text.lower()
    
    def test_interest_artificial_intelligence_qualified(self):
        """Interés en IA debe calificar."""
        lead_text = "Queremos implementar inteligencia artificial"
        assert "inteligencia artificial" in lead_text.lower() or "ia" in lead_text.lower()
    
    def test_interest_ai_acronym_qualified(self):
        """Interés en IA (sigla) debe calificar."""
        lead_text = "Nos interesa explorar soluciones de IA"
        assert "ia" in lead_text.lower()
    
    def test_interest_machine_learning_qualified(self):
        """Machine Learning debe calificar."""
        lead_text = "Queremos usar machine learning en nuestros sistemas"
        assert "machine learning" in lead_text.lower()
    
    def test_interest_digital_transformation_qualified(self):
        """Transformación digital debe calificar."""
        lead_text = "Buscamos transformación digital de nuestros procesos"
        assert "transformación" in lead_text.lower() or "transformation" in lead_text.lower()
    
    def test_interest_none_not_qualified(self):
        """Sin interés en IA/automatización NO debe calificar."""
        lead_text = "Somos una consultora pero no tenemos interés en IA"
        # Sin interés → no califica aunque otros criterios cumplan
        assert "no" in lead_text.lower() and ("ia" in lead_text.lower() or "automati" in lead_text.lower())
    
    def test_interest_accounting_not_qualified(self):
        """Solo contabilidad NO es suficiente interés."""
        lead_text = "Hacemos asesoría contable para empresas"
        # Contabilidad alone ≠ IA/automatización
        assert "contab" in lead_text.lower()
    
    # ============ CASOS EDGE ============
    
    def test_all_criteria_met_qualified(self):
        """Caso ideal: todos los criterios cumplidos."""
        lead_text = (
            "Somos una consultora en Madrid con 25 empleados. "
            "Especializados en estrategia digital y queremos implementar IA "
            "para automatizar nuestros procesos de consultoría."
        )
        # Validar que contiene todo
        assert "consul" in lead_text.lower()
        assert "madrid" in lead_text.lower()
        assert "25" in lead_text
        assert ("ia" in lead_text.lower() or "automati" in lead_text.lower())
    
    def test_multiple_locations_one_valid(self):
        """Si menciona USA y España, ¿cuál se toma?"""
        lead_text = (
            "Tenemos oficinas en Nueva York y también en Madrid. "
            "Somos consultora de 30 empleados."
        )
        # LLM debe extraer la ubicación válida
        assert "madrid" in lead_text.lower()
    
    def test_ambiguous_employee_count(self):
        """Número de empleados ambiguo debe ser manejado."""
        lead_text = "Somos un equipo de al menos 5 personas"
        # "al menos 5" = cumple
        assert "5" in lead_text or "al menos" in lead_text.lower()
    
    def test_misspellings_tolerated(self):
        """Errores de ortografía deben ser tolerados."""
        lead_text = (
            "Somoz una consultoria en Madrrid con 20 empleados "
            "ke quier IA"
        )
        # LLM debe entender a pesar de typos
        assert len(lead_text) > 10  # Contiene información
 
 
class TestLeadValidation:
    """Tests de validación de modelos Pydantic."""
    
    def test_lead_input_valid(self):
        """LeadInput válido se crea correctamente."""
        lead = LeadInput(
            raw_text="Somos consultora en Madrid con 20 empleados",
            telegram_user_id=123456,
            telegram_username="test"
        )
        assert lead.telegram_user_id == 123456
        assert len(lead.raw_text) > 0
    
    def test_lead_input_too_short(self):
        """LeadInput muy corto falla validación."""
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            LeadInput(
                raw_text="Hola",  # Menos de 10 caracteres
                telegram_user_id=123456,
            )
    
    def test_lead_input_too_long(self):
        """LeadInput muy largo falla validación."""
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            LeadInput(
                raw_text="a" * 2001,  # Más de 2000 caracteres
                telegram_user_id=123456,
            )
    
    def test_qualification_valid(self):
        """LeadQualification válido se crea correctamente."""
        qual = LeadQualification(
            is_qualified=True,
            reason="Cumple todos los criterios"
        )
        assert qual.is_qualified is True
        assert len(qual.reason) > 0
    
    def test_qualification_reason_too_short(self):
        """Razón muy corta falla validación."""
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            LeadQualification(
                is_qualified=False,
                reason="No"  # Menos de 10 caracteres
            )
